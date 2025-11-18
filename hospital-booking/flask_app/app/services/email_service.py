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
            'app.services.email_service.send_otp_email',  # Use string path instead of function reference
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