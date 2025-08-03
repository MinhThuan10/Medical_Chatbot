from sqlalchemy import text

class Chat_data:

    def get_all_chat_data(self, user_id, conservation_id, db):
        checked_user = db.execute(
            text("SELECT user_id FROM conservation WHERE id = :conservation_id"),
            {"conservation_id": conservation_id}
        )
        row = checked_user.fetchone()
        if not row or row['user_id'] != user_id:
            return []
        result = db.execute(
            text("SELECT * FROM chat_data WHERE conservation_id = :conservation_id"),
            {"conservation_id": conservation_id}
        )
        return [dict(row) for row in result.fetchall()]
    
    def get_chat_data_history(self, user_id, conservation_id, db):
        checked_user = db.execute(
            text("SELECT user_id FROM conservation WHERE id = :conservation_id"),
            {"conservation_id": conservation_id}
        )
        row = checked_user.fetchone()
        if not row or row['user_id'] != user_id:
            return {}
    
        result = db.execute(
            text("SELECT * FROM chat_data WHERE conservation_id = :conservation_id ORDER BY stt DESC LIMIT 1"),
            {"conservation_id": conservation_id,}
        )
        row = result.fetchone()
        if row:
            return dict(row)
        return {}
    
    def insert_chat_data(self, db, user_id, conservation_id, question_text, answer_text):
        # Check if the user_id matches the conservation_id
        checked_user = db.execute(
            text("SELECT user_id FROM conservation WHERE id = :conservation_id"),
            {"conservation_id": conservation_id}
        )
        row = checked_user.fetchone()
        if not row or row['user_id'] != user_id:
            raise ValueError("User ID does not match the conservation ID")
        # Insert chat data
        result = db.execute(
            text("SELECT MAX(stt) as stt FROM chat_data WHERE conservation_id = :conservation_id"),
            {"conservation_id": conservation_id}
        ).fetchone()

        stt = result['stt'] + 1 if result['stt'] is not None else 0

        print(f"stt: {stt}")
        result = db.execute(
            text(
                "INSERT INTO chat_data (conservation_id, question_text, answer_text, stt) "
                "VALUES (:conservation_id, :question_text, :answer_text, :stt)"
            ),
            {
                "conservation_id": conservation_id,
                "question_text": question_text,
                "answer_text": answer_text,
                "stt": stt
            }
        )
        db.commit()
        return result.lastrowid