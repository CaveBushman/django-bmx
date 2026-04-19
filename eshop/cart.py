CART_SESSION_KEY = "eshop_cart"


class Cart:
    def __init__(self, request):
        self._session = request.session
        self._cart = self._session.setdefault(CART_SESSION_KEY, {})

    def _save(self):
        self._session.modified = True

    def add(self, variant_id, quantity=1):
        key = str(variant_id)
        self._cart[key] = self._cart.get(key, 0) + quantity
        self._save()

    def set(self, variant_id, quantity):
        key = str(variant_id)
        if quantity <= 0:
            self._cart.pop(key, None)
        else:
            self._cart[key] = quantity
        self._save()

    def get_quantity(self, variant_id):
        return self._cart.get(str(variant_id), 0)

    def remove(self, variant_id):
        self._cart.pop(str(variant_id), None)
        self._save()

    def clear(self):
        self._session[CART_SESSION_KEY] = {}
        self._cart = self._session[CART_SESSION_KEY]
        self._save()

    def __len__(self):
        return sum(self._cart.values())

    def __bool__(self):
        return bool(self._cart)

    def variant_ids(self):
        return [int(k) for k in self._cart]

    def raw(self):
        return dict(self._cart)
