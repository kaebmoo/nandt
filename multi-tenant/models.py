# models.py - Enhanced with optimizations
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from datetime import timezone
import uuid
from enum import Enum
from sqlalchemy import Index, event, Numeric # Import Numeric for Decimal type

from sqlalchemy.ext.hybrid import hybrid_property
# Import Cache for caching support
try:
    from flask_caching import Cache
    cache = Cache()
except ImportError:
    # Fallback cache implementation if flask_caching is not installed
    class DummyCache:
        def get(self, key):
            return None
        def set(self, key, value, timeout=None):
            pass
        def init_app(self, app):
            pass
    cache = DummyCache()

db = SQLAlchemy()

class SubscriptionPlan(Enum):
    FREE = "free"
    BASIC = "basic" 
    PREMIUM = "premium"

class SubscriptionStatus(Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    TRIAL = "trial"

class UserRole(Enum):
    ADMIN = "admin"
    STAFF = "staff"

class Organization(db.Model):
    __tablename__ = 'organizations'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False, index=True)
    contact_email = db.Column(db.String(255), nullable=False, index=True)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    
    # TeamUp Integration
    teamup_calendar_id = db.Column(db.String(255), unique=True, index=True)
    
    # Subscription
    subscription_plan = db.Column(db.Enum(SubscriptionPlan), default=SubscriptionPlan.FREE, index=True)
    subscription_status = db.Column(db.Enum(SubscriptionStatus), default=SubscriptionStatus.TRIAL, index=True)
    subscription_expires_at = db.Column(db.DateTime(timezone=True), index=True)
    trial_ends_at = db.Column(db.DateTime(timezone=True), index=True)
    
    # Usage Limits
    max_appointments_per_month = db.Column(db.Integer, default=50)
    max_staff_users = db.Column(db.Integer, default=2)
    
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    deleted_at = db.Column(db.DateTime(timezone=True))
    
    # Relationships with lazy loading
    users = db.relationship('User', backref='organization', lazy='dynamic', 
                            primaryjoin="and_(Organization.id==User.organization_id, User.is_deleted==False)")
    subscriptions = db.relationship('Subscription', backref='organization', lazy='dynamic')
    usage_stats = db.relationship('UsageStat', backref='organization', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='organization', lazy='dynamic')
    teamup_calendars = db.relationship('TeamUpCalendar', backref='organization', lazy='dynamic')
    subcalendars = db.relationship('OrganizationSubcalendar', backref='organization', lazy='dynamic')
    
    def __init__(self, **kwargs):
        super(Organization, self).__init__(**kwargs)
        # Set trial period (14 days) - ใช้ timezone-aware
        now_utc = datetime.now(timezone.utc)
        self.trial_ends_at = now_utc + timedelta(days=14)
        self.subscription_expires_at = self.trial_ends_at
    
    @hybrid_property
    def is_trial_expired(self):
        """ตรวจสอบว่า trial หมดอายุแล้วหรือไม่ - แก้ไข timezone issue"""
        if not self.trial_ends_at:
            return True
        
        # แก้ไข: ตรวจสอบและแปลง timezone
        trial_end_aware = self.trial_ends_at
        
        # ถ้า trial_ends_at ไม่มี timezone info ให้เพิ่ม UTC
        if trial_end_aware.tzinfo is None:
            trial_end_aware = trial_end_aware.replace(tzinfo=timezone.utc)
        
        return datetime.now(timezone.utc) > trial_end_aware
    
    @hybrid_property
    def is_subscription_active(self):
        """ตรวจสอบว่า subscription ยังใช้งานได้หรือไม่ - แก้ไข timezone issue"""
        if self.subscription_status != SubscriptionStatus.ACTIVE:
            return False
            
        if not self.subscription_expires_at:
            return False
        
        # แก้ไข: ตรวจสอบและแปลง timezone
        expires_at_aware = self.subscription_expires_at
        
        # ถ้า subscription_expires_at ไม่มี timezone info ให้เพิ่ม UTC
        if expires_at_aware.tzinfo is None:
            expires_at_aware = expires_at_aware.replace(tzinfo=timezone.utc)
        
        return datetime.now(timezone.utc) < expires_at_aware
    
    def can_create_appointment(self):
        """Check if organization can create more appointments with caching"""
        if self.subscription_plan == SubscriptionPlan.PREMIUM:
            return True
        
        # Use cache for current month usage
        cache_key = f"usage_{self.id}_{datetime.now().strftime('%Y-%m')}"
        current_usage = cache.get(cache_key)
        
        if current_usage is None:
            current_usage = self.get_current_month_usage()
            cache.set(cache_key, current_usage, timeout=300)  # 5 minutes cache
        
        return current_usage < self.max_appointments_per_month
    
    def can_add_staff(self):
        """Check staff limit with query optimization"""
        current_staff_count = self.users.filter_by(
            role=UserRole.STAFF,
            is_active=True,
            is_deleted=False
        ).count()
        return current_staff_count < self.max_staff_users
    
    def get_current_month_usage(self):
        """Get current month usage with timezone-aware comparison"""
        # แก้ไข: ใช้ timezone-aware datetime
        current_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        usage = db.session.query(db.func.sum(UsageStat.appointments_created)).filter(
            UsageStat.organization_id == self.id,
            UsageStat.date >= current_month.date()  # เปรียบเทียบแค่ date part
        ).scalar()
        
        return usage or 0
    
    def soft_delete(self):
        """Soft delete organization"""
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        db.session.commit()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False, index=True)
    
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.Enum(UserRole), default=UserRole.STAFF, index=True)
    
    # 2FA
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32))
    
    # Account Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    email_verified = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime(timezone=True), index=True)
    
    # Password Reset
    reset_token = db.Column(db.String(100), index=True)
    reset_token_expires = db.Column(db.DateTime(timezone=True))
    
    # Soft delete
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    deleted_at = db.Column(db.DateTime(timezone=True))
    
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')
    
    # Indexes for better performance
    __table_args__ = (
        Index('idx_user_org_role', 'organization_id', 'role'),
        Index('idx_user_org_active', 'organization_id', 'is_active'),
        Index('idx_user_email_active', 'email', 'is_active'),
    )
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256:100000')
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    def generate_reset_token(self):
        self.reset_token = str(uuid.uuid4())
        self.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        return self.reset_token
    
    def is_reset_token_valid(self):
        """ตรวจสอบว่า reset token ยังใช้งานได้หรือไม่ - แก้ไข timezone issue"""
        if not self.reset_token or not self.reset_token_expires:
            return False
        
        # แก้ไข: ตรวจสอบและแปลง timezone
        expires_at_aware = self.reset_token_expires
        
        # ถ้า reset_token_expires ไม่มี timezone info ให้เพิ่ม UTC
        if expires_at_aware.tzinfo is None:
            expires_at_aware = expires_at_aware.replace(tzinfo=timezone.utc)
        
        return datetime.now(timezone.utc) < expires_at_aware    

    def ensure_timezone_aware(dt_obj, default_tz=timezone.utc):
        """
        Helper function to ensure datetime object is timezone-aware
        แปลง naive datetime เป็น timezone-aware
        """
        if dt_obj is None:
            return None
        
        if dt_obj.tzinfo is None:
            return dt_obj.replace(tzinfo=default_tz)
        
        return dt_obj    
    
    def soft_delete(self):
        """Soft delete user"""
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.is_active = False
        db.session.commit()

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    
    plan_type = db.Column(db.Enum(SubscriptionPlan), nullable=False)
    billing_cycle = db.Column(db.String(10), nullable=False)  # 'monthly', 'yearly'
    
    amount = db.Column(Numeric(10, 2), nullable=False) # Changed from db.Decimal to Numeric
    currency = db.Column(db.String(3), default='THB')
    
    # Stripe Integration
    stripe_subscription_id = db.Column(db.String(255))
    stripe_customer_id = db.Column(db.String(255))
    stripe_payment_method_id = db.Column(db.String(255))
    
    # Billing
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True))
    next_billing_date = db.Column(db.DateTime(timezone=True))
    
    status = db.Column(db.Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class UsageStat(db.Model):
    __tablename__ = 'usage_stats'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False, index=True)
    
    date = db.Column(db.Date, nullable=False, index=True)
    appointments_created = db.Column(db.Integer, default=0)
    appointments_updated = db.Column(db.Integer, default=0)
    staff_active = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        db.UniqueConstraint('organization_id', 'date', name='unique_org_date'),
        Index('idx_usage_org_date', 'organization_id', 'date'),
    )
    
    @classmethod
    def get_or_create_today(cls, organization_id):
        """Get or create today's usage stat"""
        today = datetime.now().date()
        usage_stat = cls.query.filter_by(
            organization_id=organization_id,
            date=today
        ).first()
        
        if not usage_stat:
            usage_stat = cls(
                organization_id=organization_id,
                date=today
            )
            db.session.add(usage_stat)
            db.session.commit()
        
        return usage_stat

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), index=True)
    
    action = db.Column(db.String(50), nullable=False, index=True)
    resource_type = db.Column(db.String(50), nullable=False, index=True)
    resource_id = db.Column(db.String(255), index=True)
    
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    __table_args__ = (
        Index('idx_audit_org_action', 'organization_id', 'action'),
        Index('idx_audit_org_resource', 'organization_id', 'resource_type'),
        Index('idx_audit_created', 'created_at'),
    )

class TeamUpCalendar(db.Model):
    """Model สำหรับเก็บ Master Calendars ของแต่ละ Organization"""
    __tablename__ = 'teamup_calendars'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    
    calendar_id = db.Column(db.String(255), unique=True, nullable=False)
    calendar_name = db.Column(db.String(255), nullable=False)
    
    is_primary = db.Column(db.Boolean, default=False)  # Calendar หลักของ org
    is_active = db.Column(db.Boolean, default=True)
    
    subcalendar_count = db.Column(db.Integer, default=0)
    max_subcalendars = db.Column(db.Integer, default=8)
    
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    subcalendars = db.relationship('OrganizationSubcalendar', backref='teamup_calendar', lazy='dynamic')

class OrganizationSubcalendar(db.Model):
    """Model สำหรับเก็บ Subcalendars mapping"""
    __tablename__ = 'organization_subcalendars'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    calendar_id = db.Column(db.String(255), db.ForeignKey('teamup_calendars.calendar_id'), nullable=False)
    
    subcalendar_id = db.Column(db.Integer, nullable=False)
    subcalendar_name = db.Column(db.String(255), nullable=False)
    
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        db.UniqueConstraint('organization_id', 'subcalendar_id'),
        db.UniqueConstraint('calendar_id', 'subcalendar_id'),
    )

# Database event listeners for automatic updates
@event.listens_for(User, 'before_update')
def receive_before_update(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)

@event.listens_for(Organization, 'before_update')
def receive_before_update_org(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)

# Pricing Plans with enhanced features
PRICING_PLANS = {
    SubscriptionPlan.FREE: {
        'name': 'ฟรี',
        'price_monthly': 0,
        'price_yearly': 0,
        'appointments_per_month': 50,
        'max_staff': 2,
        'features': [
            'นัดหมายพื้นฐาน 50 รายการ/เดือน',
            'การจัดการปฏิทิน',
            'รายงานเบื้องต้น',
            'เจ้าหน้าที่ 2 คน'
        ],
        'limitations': [
            'ไม่มีการสำรองข้อมูล',
            'ไม่มี API Access',
            'ซัพพอร์ตมาตรฐาน'
        ]
    },
    SubscriptionPlan.BASIC: {
        'name': 'เบสิก',
        'price_monthly': 990,
        'price_yearly': 9900,
        'appointments_per_month': 500,
        'max_staff': 10,
        'features': [
            'นัดหมาย 500 รายการ/เดือน',
            'การนำเข้าข้อมูล CSV',
            'รายงานละเอียด',
            'การสำรองข้อมูลอัตโนมัติ',
            'เจ้าหน้าที่ 10 คน',
            'ซัพพอร์ตทางอีเมล'
        ]
    },
    SubscriptionPlan.PREMIUM: {
        'name': 'พรีเมียม',
        'price_monthly': 2990,
        'price_yearly': 29900,
        'appointments_per_month': -1,  # unlimited
        'max_staff': -1,  # unlimited
        'features': [
            'นัดหมายไม่จำกัด',
            'เจ้าหน้าที่ไม่จำกัด',
            'API Access เต็มรูปแบบ',
            'การรายงานขั้นสูง',
            'การสำรองข้อมูลแบบ Real-time',
            'การสนับสนุนแบบเร่งด่วน 24/7',
            'Custom integrations',
            'White-label options'
        ]
    }
}
