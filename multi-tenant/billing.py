# billing.py
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
import stripe
import os
from datetime import datetime, timedelta
from models import db, Organization, Subscription, SubscriptionPlan, SubscriptionStatus, PRICING_PLANS
from datetime import timezone

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

@billing_bp.route('/choose-plan')
@login_required
def choose_plan():
    """หน้าเลือกแพ็คเกจ"""
    # เฉพาะ Admin เท่านั้นที่เปลี่ยนแพ็คเกจได้
    if current_user.user.role.value != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('index'))
    
    current_plan = current_user.organization.subscription_plan
    return render_template('billing/choose_plan.html', 
                         pricing_plans=PRICING_PLANS,
                         current_plan=current_plan,
                         organization=current_user.organization)

@billing_bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """สร้าง Stripe Checkout Session"""
    try:
        if current_user.user.role.value != 'admin':
            return jsonify({'error': 'คุณไม่มีสิทธิ์ดำเนินการนี้'}), 403
        
        data = request.get_json()
        plan_type = data.get('plan_type')
        billing_cycle = data.get('billing_cycle', 'monthly')
        
        if plan_type not in [plan.value for plan in SubscriptionPlan]:
            return jsonify({'error': 'แพ็คเกจไม่ถูกต้อง'}), 400
        
        plan_enum = SubscriptionPlan(plan_type)
        
        if plan_enum == SubscriptionPlan.FREE:
            # สำหรับแพ็คเกจฟรี ไม่ต้องผ่าน Stripe
            return upgrade_to_free_plan()
        
        # คำนวณราคา
        price_key = f'price_{billing_cycle}'
        amount = PRICING_PLANS[plan_enum][price_key]
        
        if amount <= 0:
            return jsonify({'error': 'ราคาไม่ถูกต้อง'}), 400
        
        # สร้าง Stripe Customer ถ้ายังไม่มี
        organization = current_user.organization
        stripe_customer_id = get_or_create_stripe_customer(organization)
        
        # สร้าง Checkout Session
        success_url = url_for('billing.payment_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}'
        cancel_url = url_for('billing.choose_plan', _external=True)
        
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'thb',
                    'unit_amount': amount * 100,  # Stripe ใช้ satang
                    'product_data': {
                        'name': f'NudDee {PRICING_PLANS[plan_enum]["name"]} - {billing_cycle_to_thai(billing_cycle)}',
                        'description': f'แพ็คเกจ {PRICING_PLANS[plan_enum]["name"]} สำหรับ {organization.name}'
                    },
                    'recurring': {
                        'interval': 'month' if billing_cycle == 'monthly' else 'year'
                    }
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'organization_id': organization.id,
                'plan_type': plan_type,
                'billing_cycle': billing_cycle
            }
        )
        
        return jsonify({'checkout_url': checkout_session.url})
        
    except stripe.error.StripeError as e:
        return jsonify({'error': f'Stripe Error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

@billing_bp.route('/payment-success')
@login_required
def payment_success():
    """หน้าแจ้งการชำระเงินสำเร็จ"""
    session_id = request.args.get('session_id')
    
    if not session_id:
        flash('ไม่พบข้อมูลการชำระเงิน', 'danger')
        return redirect(url_for('billing.choose_plan'))
    
    try:
        # ดึงข้อมูล session จาก Stripe
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        
        if checkout_session.payment_status == 'paid':
            flash('ชำระเงินสำเร็จ! แพ็คเกจของคุณจะเริ่มใช้งานในไม่ช้า', 'success')
        else:
            flash('การชำระเงินยังไม่เสร็จสิ้น กรุณารอสักครู่', 'warning')
            
        return render_template('billing/payment_success.html', 
                             session=checkout_session,
                             organization=current_user.organization)
        
    except stripe.error.StripeError as e:
        flash(f'เกิดข้อผิดพลาดในการตรวจสอบการชำระเงิน: {str(e)}', 'danger')
        return redirect(url_for('billing.choose_plan'))

@billing_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """รับ webhook จาก Stripe"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        current_app.logger.error(f"Invalid payload: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        current_app.logger.error(f"Invalid signature: {e}")
        return 'Invalid signature', 400
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        handle_checkout_session_completed(event['data']['object'])
    elif event['type'] == 'invoice.payment_succeeded':
        handle_invoice_payment_succeeded(event['data']['object'])
    elif event['type'] == 'invoice.payment_failed':
        handle_invoice_payment_failed(event['data']['object'])
    elif event['type'] == 'customer.subscription.deleted':
        handle_subscription_deleted(event['data']['object'])
    else:
        current_app.logger.info(f"Unhandled event type: {event['type']}")
    
    return 'Success', 200

@billing_bp.route('/billing-history')
@login_required
def billing_history():
    """หน้าประวัติการเรียกเก็บเงิน"""
    if current_user.user.role.value != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('index'))
    
    try:
        organization = current_user.organization
        subscriptions = Subscription.query.filter_by(
            organization_id=organization.id
        ).order_by(Subscription.created_at.desc()).all()
        
        # ดึงข้อมูล invoices จาก Stripe ถ้ามี customer ID
        stripe_invoices = []
        if hasattr(organization, 'stripe_customer_id') and organization.stripe_customer_id:
            try:
                invoices = stripe.Invoice.list(
                    customer=organization.stripe_customer_id,
                    limit=20
                )
                stripe_invoices = invoices.data
            except stripe.error.StripeError as e:
                current_app.logger.error(f"Error fetching invoices: {e}")
        
        return render_template('billing/billing_history.html',
                             subscriptions=subscriptions,
                             stripe_invoices=stripe_invoices,
                             organization=organization)
        
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
        return redirect(url_for('index'))

@billing_bp.route('/cancel-subscription', methods=['POST'])
@login_required
def cancel_subscription():
    """ยกเลิกการสมัครสมาชิก"""
    if current_user.user.role.value != 'admin':
        return jsonify({'error': 'คุณไม่มีสิทธิ์ดำเนินการนี้'}), 403
    
    try:
        organization = current_user.organization
        current_subscription = Subscription.query.filter_by(
            organization_id=organization.id,
            status=SubscriptionStatus.ACTIVE
        ).first()
        
        if not current_subscription:
            return jsonify({'error': 'ไม่พบการสมัครสมาชิกที่ใช้งานอยู่'}), 400
        
        if current_subscription.stripe_subscription_id:
            # ยกเลิกใน Stripe
            stripe.Subscription.delete(current_subscription.stripe_subscription_id)
        
        # อัปเดตสถานะในฐานข้อมูล
        current_subscription.status = SubscriptionStatus.CANCELLED
        organization.subscription_status = SubscriptionStatus.CANCELLED
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'ยกเลิกการสมัครสมาชิกสำเร็จ'})
        
    except stripe.error.StripeError as e:
        return jsonify({'error': f'Stripe Error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

@billing_bp.route('/update-payment-method')
@login_required
def update_payment_method():
    """หน้าอัปเดตวิธีการชำระเงิน"""
    if current_user.user.role.value != 'admin':
        flash('คุณไม่มีสิทธิ์เข้าถึงหน้านี้', 'danger')
        return redirect(url_for('index'))
    
    try:
        organization = current_user.organization
        stripe_customer_id = get_or_create_stripe_customer(organization)
        
        # สร้าง Setup Intent สำหรับอัปเดตการชำระเงิน
        setup_intent = stripe.SetupIntent.create(
            customer=stripe_customer_id,
            usage='off_session'
        )
        
        return render_template('billing/update_payment_method.html',
                             client_secret=setup_intent.client_secret,
                             stripe_pk=os.getenv('STRIPE_PUBLISHABLE_KEY'),
                             organization=organization)
        
    except stripe.error.StripeError as e:
        flash(f'Stripe Error: {str(e)}', 'danger')
        return redirect(url_for('billing.choose_plan'))
    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {str(e)}', 'danger')
        return redirect(url_for('billing.choose_plan'))

# Helper Functions
def get_or_create_stripe_customer(organization):
    """ดึงหรือสร้าง Stripe Customer"""
    current_subscription = Subscription.query.filter_by(
        organization_id=organization.id
    ).first()
    
    if current_subscription and current_subscription.stripe_customer_id:
        return current_subscription.stripe_customer_id
    
    # สร้าง customer ใหม่
    customer = stripe.Customer.create(
        email=organization.contact_email,
        name=organization.name,
        metadata={
            'organization_id': organization.id
        }
    )
    
    return customer.id

def upgrade_to_free_plan():
    """อัปเกรดเป็นแพ็คเกจฟรี"""
    try:
        organization = current_user.organization
        
        # อัปเดตแพ็คเกจ
        organization.subscription_plan = SubscriptionPlan.FREE
        organization.subscription_status = SubscriptionStatus.ACTIVE
        organization.subscription_expires_at = datetime.now(timezone.utc) + timedelta(days=365)  # 1 ปี
        organization.max_appointments_per_month = PRICING_PLANS[SubscriptionPlan.FREE]['appointments_per_month']
        organization.max_staff_users = PRICING_PLANS[SubscriptionPlan.FREE]['max_staff']
        
        # สร้างระเบียน subscription
        subscription = Subscription(
            organization_id=organization.id,
            plan_type=SubscriptionPlan.FREE,
            billing_cycle='yearly',
            amount=0,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=datetime.now(timezone.utc),
            current_period_end=organization.subscription_expires_at
        )
        
        db.session.add(subscription)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'redirect_url': url_for('index'),
            'message': 'เปลี่ยนเป็นแพ็คเกจฟรีสำเร็จ'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'เกิดข้อผิดพลาด: {str(e)}'}), 500

def handle_checkout_session_completed(session):
    """จัดการเมื่อการชำระเงินเสร็จสิ้น"""
    try:
        organization_id = session['metadata']['organization_id']
        plan_type = session['metadata']['plan_type']
        billing_cycle = session['metadata']['billing_cycle']
        
        organization = Organization.query.get(organization_id)
        if not organization:
            current_app.logger.error(f"Organization not found: {organization_id}")
            return
        
        plan_enum = SubscriptionPlan(plan_type)
        
        # ดึงข้อมูล subscription จาก Stripe
        stripe_subscription = stripe.Subscription.retrieve(session['subscription'])
        
        # อัปเดตองค์กร
        organization.subscription_plan = plan_enum
        organization.subscription_status = SubscriptionStatus.ACTIVE
        organization.subscription_expires_at = datetime.fromtimestamp(stripe_subscription['current_period_end'])
        organization.max_appointments_per_month = PRICING_PLANS[plan_enum]['appointments_per_month']
        organization.max_staff_users = PRICING_PLANS[plan_enum]['max_staff']
        
        # สร้างหรืออัปเดต subscription record
        subscription = Subscription.query.filter_by(
            organization_id=organization_id,
            status=SubscriptionStatus.ACTIVE
        ).first()
        
        if not subscription:
            subscription = Subscription(organization_id=organization_id)
            db.session.add(subscription)
        
        subscription.plan_type = plan_enum
        subscription.billing_cycle = billing_cycle
        subscription.amount = PRICING_PLANS[plan_enum][f'price_{billing_cycle}']
        subscription.stripe_subscription_id = stripe_subscription['id']
        subscription.stripe_customer_id = stripe_subscription['customer']
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.current_period_start = datetime.fromtimestamp(stripe_subscription['current_period_start'])
        subscription.current_period_end = datetime.fromtimestamp(stripe_subscription['current_period_end'])
        subscription.next_billing_date = subscription.current_period_end
        
        db.session.commit()
        
        current_app.logger.info(f"Subscription activated for organization {organization_id}")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error handling checkout session completed: {e}")

def handle_invoice_payment_succeeded(invoice):
    """จัดการเมื่อการชำระเงินสำเร็จ"""
    try:
        subscription_id = invoice['subscription']
        if not subscription_id:
            return
        
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        customer_id = stripe_subscription['customer']
        
        # หา organization จาก customer ID
        subscription = Subscription.query.filter_by(
            stripe_customer_id=customer_id
        ).first()
        
        if not subscription:
            current_app.logger.error(f"Subscription not found for customer: {customer_id}")
            return
        
        organization = subscription.organization
        
        # อัปเดตวันหมดอายุ
        organization.subscription_expires_at = datetime.fromtimestamp(stripe_subscription['current_period_end'])
        organization.subscription_status = SubscriptionStatus.ACTIVE
        
        subscription.current_period_start = datetime.fromtimestamp(stripe_subscription['current_period_start'])
        subscription.current_period_end = datetime.fromtimestamp(stripe_subscription['current_period_end'])
        subscription.next_billing_date = subscription.current_period_end
        subscription.status = SubscriptionStatus.ACTIVE
        
        db.session.commit()
        
        current_app.logger.info(f"Payment succeeded for organization {organization.id}")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error handling invoice payment succeeded: {e}")

def handle_invoice_payment_failed(invoice):
    """จัดการเมื่อการชำระเงินล้มเหลว"""
    try:
        subscription_id = invoice['subscription']
        if not subscription_id:
            return
        
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        customer_id = stripe_subscription['customer']
        
        subscription = Subscription.query.filter_by(
            stripe_customer_id=customer_id
        ).first()
        
        if not subscription:
            return
        
        organization = subscription.organization
        
        # ระงับบัญชีชั่วคราว
        organization.subscription_status = SubscriptionStatus.SUSPENDED
        subscription.status = SubscriptionStatus.SUSPENDED
        
        db.session.commit()
        
        # ส่งอีเมลแจ้งเตือน (implement ตามต้องการ)
        # send_payment_failed_email(organization)
        
        current_app.logger.warning(f"Payment failed for organization {organization.id}")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error handling invoice payment failed: {e}")

def handle_subscription_deleted(subscription):
    """จัดการเมื่อการสมัครสมาชิกถูกยกเลิก"""
    try:
        customer_id = subscription['customer']
        
        subscription_record = Subscription.query.filter_by(
            stripe_customer_id=customer_id
        ).first()
        
        if not subscription_record:
            return
        
        organization = subscription_record.organization
        
        # เปลี่ยนเป็นแพ็คเกจฟรี
        organization.subscription_plan = SubscriptionPlan.FREE
        organization.subscription_status = SubscriptionStatus.ACTIVE
        organization.max_appointments_per_month = PRICING_PLANS[SubscriptionPlan.FREE]['appointments_per_month']
        organization.max_staff_users = PRICING_PLANS[SubscriptionPlan.FREE]['max_staff']
        
        subscription_record.status = SubscriptionStatus.CANCELLED
        
        db.session.commit()
        
        current_app.logger.info(f"Subscription cancelled for organization {organization.id}")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error handling subscription deleted: {e}")

def billing_cycle_to_thai(cycle):
    """แปลงรอบการเรียกเก็บเงินเป็นภาษาไทย"""
    return 'รายเดือน' if cycle == 'monthly' else 'รายปี'