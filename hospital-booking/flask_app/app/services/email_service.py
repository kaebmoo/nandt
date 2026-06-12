# flask_app/app/services/email_service.py
import os
import logging
from flask import render_template
from flask_mail import Message, Mail
from .redis_connection import redis_manager

logger = logging.getLogger(__name__)

def send_otp_email(recipient, otp, booking_info=None):
    """Send OTP via email with Flask app context"""
    from app import create_app
    
    app = create_app()
    mail = Mail(app)
    
    with app.app_context():
        try:
            msg = Message(
                subject='รหัส OTP สำหรับค้นหานัดหมาย',
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[recipient]
            )
            
            # HTML version
            msg.html = render_template('emails/otp.html', 
                                     otp=otp, 
                                     booking_info=booking_info)
            
            # Text version
            msg.body = render_template('emails/otp.txt', 
                                     otp=otp, 
                                     booking_info=booking_info)
            
            mail.send(msg)
            logger.info(f"Successfully sent OTP email to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Email sending failed for {recipient}: {e}", exc_info=True)
            return False

def queue_otp_email(recipient, otp, booking_info=None):
    """Queue email for background sending"""
    try:
        queue = redis_manager.get_queue('default')
        job = queue.enqueue(
            send_otp_email,
            recipient=recipient,
            otp=otp,
            booking_info=booking_info,
            job_timeout='5m'  # Set timeout for email jobs
        )
        logger.info(f"Queued OTP email job {job.id} for {recipient}")
        return job.id
    except Exception as e:
        logger.error(f"Failed to queue OTP email for {recipient}: {e}", exc_info=True)
        # Fallback: try to send directly if queue fails
        try:
            if send_otp_email(recipient, otp, booking_info):
                logger.info(f"Sent email directly after queue failure for {recipient}")
                return "direct_send"
        except:
            pass
        return None

def send_password_reset_email(recipient, otp):
    """Send password reset OTP via email with Flask app context"""
    from app import create_app

    app = create_app()
    mail = Mail(app)

    with app.app_context():
        try:
            msg = Message(
                subject='รหัสยืนยันสำหรับตั้งรหัสผ่านใหม่ - NudDee',
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[recipient]
            )

            # HTML version
            msg.html = render_template('emails/password_reset.html', otp=otp)

            # Text version
            msg.body = render_template('emails/password_reset.txt', otp=otp)

            mail.send(msg)
            logger.info(f"Successfully sent password reset email to {recipient}")
            return True

        except Exception as e:
            logger.error(f"Password reset email failed for {recipient}: {e}", exc_info=True)
            return False

def queue_password_reset_email(recipient, otp):
    """Queue password reset email for background sending"""
    try:
        queue = redis_manager.get_queue('default')
        job = queue.enqueue(
            send_password_reset_email,
            recipient=recipient,
            otp=otp,
            job_timeout='5m'
        )
        logger.info(f"Queued password reset email job {job.id} for {recipient}")
        return job.id
    except Exception as e:
        logger.error(f"Failed to queue password reset email for {recipient}: {e}", exc_info=True)
        # Fallback: try to send directly if queue fails
        try:
            if send_password_reset_email(recipient, otp):
                logger.info(f"Sent password reset email directly after queue failure for {recipient}")
                return "direct_send"
        except:
            pass
        return None