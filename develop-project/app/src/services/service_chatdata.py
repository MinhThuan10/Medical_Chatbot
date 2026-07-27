import json
from sqlalchemy import text


class Chat_data():
    # def _ensure_citations_column(self, db):
    #     table_info = db.execute(text("PRAGMA table_info(chat_data)")).fetchall()
    #     columns = {column[1] for column in table_info}
    #     if "citations_json" not in columns:
    #         db.execute(text("ALTER TABLE chat_data ADD COLUMN citations_json TEXT"))
    #         db.commit()

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

    def insert_chat_data(self, db, user_id, conservation_id, question_text, answer_text, citations_json=None):
        # self._ensure_citations_column(db)
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
                "INSERT INTO chat_data (conservation_id, question_text, answer_text, citations_json, stt) "
                "VALUES (:conservation_id, :question_text, :answer_text, :citations_json, :stt)"
            ),
            {
                "conservation_id": conservation_id,
                "question_text": question_text,
                "answer_text": answer_text,
                "citations_json": json.dumps(citations_json, ensure_ascii=False),
                "stt": stt
            }
        )
        db.commit()
        return result.lastrowid
    