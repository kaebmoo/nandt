import sys
import os
import getpass
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from shared_db.database import engine, SessionLocal
from shared_db.models import User, UserRole

def reset_super_admin_password():
    db = SessionLocal()
    try:
        # Ensure we are in public schema
        db.execute(text("SET search_path TO public"))
        
        # Find all super admins
        super_admins = db.query(User).filter(User.role == UserRole.SUPER_ADMIN).all()
        
        if not super_admins:
            print("No Super Admin found!")
            return

        print("\n--- Super Admin Users ---")
        for i, admin in enumerate(super_admins):
            print(f"{i+1}. {admin.email} (Name: {admin.name})")
            
        choice = input("\nSelect admin to reset (number) or 'q' to quit: ")
        if choice.lower() == 'q':
            return
            
        try:
            index = int(choice) - 1
            if 0 <= index < len(super_admins):
                target_user = super_admins[index]
                new_password = getpass.getpass(f"Enter new password for {target_user.email}: ")
                confirm_password = getpass.getpass("Confirm password: ")
                
                if new_password != confirm_password:
                    print("Passwords do not match!")
                    return
                
                target_user.set_password(new_password)
                db.commit()
                print(f"\n✅ Password for {target_user.email} has been reset successfully.")
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input.")
            
    finally:
        db.close()

if __name__ == "__main__":
    reset_super_admin_password()
