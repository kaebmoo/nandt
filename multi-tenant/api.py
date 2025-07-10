# api.py - Create this new file for API endpoints

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models import db, UsageStat, AuditLog, Organization
from hybrid_teamup_strategy import get_hybrid_teamup_api

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """API heartbeat endpoint for frontend polling"""
    try:
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.utcnow().isoformat(),
            'server': 'NudDee SaaS'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@api_bp.route('/usage-stats', methods=['GET'])
@login_required
def get_usage_stats():
    """Get usage statistics for current organization"""
    try:
        # Create TeamUp API instance
        teamup_api = get_hybrid_teamup_api(
            organization_id=current_user.user.organization_id,
            user_id=current_user.user.id
        )
        
        # Get organization stats
        stats = teamup_api.get_organization_stats()
        
        # Get current month usage
        current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_stats = UsageStat.query.filter(
            UsageStat.organization_id == current_user.user.organization_id,
            UsageStat.date >= current_month
        ).all()
        
        total_appointments = sum(stat.appointments_created for stat in monthly_stats)
        total_updates = sum(stat.appointments_updated for stat in monthly_stats)
        
        # Get organization limits
        organization = current_user.organization
        max_appointments = organization.max_appointments_per_month
        max_staff = organization.max_staff_users
        
        # Calculate usage percentages
        appointment_usage = (total_appointments / max_appointments * 100) if max_appointments > 0 else 0
        
        return jsonify({
            'success': True,
            'data': {
                'monthly_appointments': total_appointments,
                'monthly_updates': total_updates,
                'max_appointments': max_appointments,
                'max_staff': max_staff,
                'appointment_usage_percent': min(appointment_usage, 100),
                'active_calendars': stats.get('active_calendars', 0),
                'active_subcalendars': stats.get('active_subcalendars', 0),
                'subscription_plan': organization.subscription_plan.value,
                'subscription_status': organization.subscription_status.value,
                'trial_expires_at': organization.trial_ends_at.isoformat() if organization.trial_ends_at else None,
                'is_trial_expired': organization.is_trial_expired,
                'can_create_appointment': organization.can_create_appointment(),
                'can_add_staff': organization.can_add_staff()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api_bp.route('/health', methods=['GET'])
def health_check():
    """System health check endpoint"""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'checks': {}
        }
        
        # Database check
        try:
            db.engine.execute('SELECT 1')
            health_status['checks']['database'] = 'healthy'
        except Exception as e:
            health_status['checks']['database'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'degraded'
        
        # Check if we can import main modules
        try:
            from models import Organization
            from hybrid_teamup_strategy import HybridTeamUpManager
            health_status['checks']['modules'] = 'healthy'
        except Exception as e:
            health_status['checks']['modules'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'degraded'
        
        # TeamUp API check (basic)
        try:
            from config import Config
            if Config.MASTER_TEAMUP_API and Config.TEMPLATE_CALENDAR_KEY:
                health_status['checks']['teamup_config'] = 'healthy'
            else:
                health_status['checks']['teamup_config'] = 'unhealthy: missing config'
                health_status['status'] = 'degraded'
        except Exception as e:
            health_status['checks']['teamup_config'] = f'unhealthy: {str(e)}'
            health_status['status'] = 'degraded'
        
        return jsonify(health_status), 200 if health_status['status'] == 'healthy' else 503
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@api_bp.route('/organization/summary', methods=['GET'])
@login_required
def organization_summary():
    """Get organization summary for dashboard"""
    try:
        organization = current_user.organization
        
        # Get recent activities
        recent_activities = AuditLog.query.filter_by(
            organization_id=organization.id
        ).order_by(AuditLog.created_at.desc()).limit(5).all()
        
        # Get today's stats
        today = datetime.now().date()
        today_stats = UsageStat.query.filter_by(
            organization_id=organization.id,
            date=today
        ).first()
        
        return jsonify({
            'success': True,
            'data': {
                'organization_name': organization.name,
                'subscription_plan': organization.subscription_plan.value,
                'subscription_status': organization.subscription_status.value,
                'today_appointments': today_stats.appointments_created if today_stats else 0,
                'today_updates': today_stats.appointments_updated if today_stats else 0,
                'recent_activities': [
                    {
                        'action': activity.action,
                        'resource_type': activity.resource_type,
                        'created_at': activity.created_at.isoformat(),
                        'user_id': activity.user_id
                    } for activity in recent_activities
                ]
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Error handlers for API blueprint
@api_bp.errorhandler(404)
def api_not_found(error):
    return jsonify({
        'success': False,
        'error': 'API endpoint not found',
        'code': 404
    }), 404

@api_bp.errorhandler(500)
def api_server_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'code': 500
    }), 500