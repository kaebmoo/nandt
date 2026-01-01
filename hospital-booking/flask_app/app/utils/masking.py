import re

def mask_phone(phone):
    """
    Mask phone number: 0812345678 -> 081-xxx-5678
    """
    if not phone:
        return ""
    
    # Simple cleaning
    clean_phone = re.sub(r'\D', '', str(phone))
    
    if len(clean_phone) < 8:
        return phone # Too short to mask safely
        
    # Keep first 3 and last 4
    return f"{clean_phone[:3]}-xxx-{clean_phone[-4:]}"

def mask_email(email):
    """
    Mask email: somchai.j@gmail.com -> s********@gmail.com
    """
    if not email or '@' not in email:
        return email
        
    parts = email.split('@')
    username = parts[0]
    domain = parts[1]
    
    if len(username) <= 2:
        masked_user = username[0] + "*" * (len(username) - 1)
    else:
        masked_user = username[0] + "*" * (len(username) - 2) + username[-1]
        
    return f"{masked_user}@{domain}"

def mask_id_card(id_card):
    """
    Mask ID Card: 1-1004-12345-12-1 -> 1-xxxx-xxxxx-xx-1
    """
    if not id_card:
        return ""
        
    clean_id = re.sub(r'\D', '', str(id_card))
    
    if len(clean_id) != 13:
        return id_card # Might not be a Thai ID card
        
    # Format: 1-xxxx-xxxxx-xx-1
    return f"{clean_id[0]}-xxxx-xxxxx-xx-{clean_id[-1]}"
