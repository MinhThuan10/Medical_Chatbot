from sqlalchemy import text

class Conservation:
    def create_conservation(self, db, user_id, name, create_day, chat_day):
        result = db.execute(
            text(
                "INSERT INTO conservation (user_id, name, create_day, chat_day) "
                "VALUES (:user_id, :name, :create_day, :chat_day)"
            ),
            {
                "user_id": user_id,
                "name": name,
                "create_day": create_day,
                "chat_day": chat_day
            }
        )
        db.commit()
        return result.lastrowid
        
    def get_all_conservations(self,user_id, db):
        result = db.execute(
            text("SELECT * FROM conservation WHERE user_id = :user_id"),
            {"user_id": user_id} 
        )
        return result.mappings().all()

    def update_conservation(self, db, user_id, conservation_id, name, chat_day):
        result = db.execute(
            text(
                "UPDATE conservation SET name = :name, chat_day = :chat_day "
                "WHERE id = :conservation_id AND user_id = :user_id"
            ),
            {
                "name": name,
                "chat_day": chat_day,
                "conservation_id": conservation_id,
                "user_id": user_id
            }
        )
        db.commit()
        return result.rowcount > 0
    
    def delete_conservation(self, db, user_id, conservation_id):

        result = db.execute(
            text(
                "DELETE FROM conservation WHERE id = :conservation_id AND user_id = :user_id"
            ),
            {
                "conservation_id": conservation_id,
                "user_id": user_id
            }
        )
        db.commit()
        return result.rowcount > 0
    