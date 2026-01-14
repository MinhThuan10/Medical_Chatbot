from sqlalchemy import text


class Chat_data():
    def get_all_chat_data(self, user_id, conservation_id, db):
        checked_user = db.execute(
            text("SELECT user_id FROM conservation WHERE id = :conservation_id"),
            {"conservation_id": conservation_id}
        )
        user_id_conservation = checked_user.fetchone()
        if not user_id_conservation or user_id_conservation[0] != user_id:
            return []
        result = db.execute(
            text("SELECT * FROM chat_data WHERE conservation_id = :conservation_id"),
            {"conservation_id": conservation_id}
        )
        rows = result.mappings().all()
        return [dict(row) for row in rows]

    def insert_chat_data(self, db, user_id, conservation_id, question_text, answer_text):
        # Check if the user_id matches the conservation_id
        checked_user = db.execute(
            text("SELECT user_id FROM conservation WHERE id = :conservation_id"),
            {"conservation_id": conservation_id}
        )
        user_id_conservation = checked_user.fetchone()
        if not user_id_conservation or user_id_conservation[0] != user_id:
            raise ValueError("User ID does not match the conservation ID")
        # Insert chat data
        result = db.execute(
            text("SELECT MAX(stt) as stt FROM chat_data WHERE conservation_id = :conservation_id"),
            {"conservation_id": conservation_id}
        ).fetchone()

        stt = result[0] + 1 if result[0] is not None else 0

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
    