from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _now():
    return datetime.now(timezone.utc)


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(32), unique=True, nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    brand = db.Column(db.String(200))
    category = db.Column(db.String(200))
    description = db.Column(db.Text)
    ingredients = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    nutriscore = db.Column(db.String(1))
    quantity = db.Column(db.Integer, nullable=False, default=0)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    # Fields a client may set directly.
    WRITABLE = (
        "barcode", "name", "brand", "category", "description",
        "ingredients", "image_url", "nutriscore", "quantity", "price",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "barcode": self.barcode,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "description": self.description,
            "ingredients": self.ingredients,
            "image_url": self.image_url,
            "nutriscore": self.nutriscore,
            "quantity": self.quantity,
            "price": float(self.price) if self.price is not None else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
