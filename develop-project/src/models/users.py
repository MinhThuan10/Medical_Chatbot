
class Users:
    def create_user(self, db, user_id, create_at, last_seen):
        db.execute(
            "INSERT INTO users (user_id, create_at, last_seen) VALUES (:user_id, :create_at, :last_seen)",
            {"user_id": user_id, "create_at": create_at, "last_seen": last_seen}
        )
        db.commit()

    def update_user(self, db, user_id, last_seen):
        db.execute(
            "UPDATE users SET last_seen = :last_seen WHERE user_id = :user_id",
            {"user_id": user_id, "last_seen": last_seen}
        )
        db.commit()
