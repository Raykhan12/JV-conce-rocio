import hashlib
import hmac
import json
from dataclasses import dataclass
from os import environ
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


class FlowConfigurationError(RuntimeError):
    pass


class FlowAPIError(RuntimeError):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class FlowPaymentOrder:
    flow_order: str
    token: str
    url: str
    payment_url: str
    raw: dict


class FlowClient:
    def __init__(self, api_key=None, secret_key=None, api_url=None, timeout=8):
        self.api_key = api_key or environ.get("FLOW_API_KEY", "")
        self.secret_key = secret_key or environ.get("FLOW_SECRET_KEY", "")
        self.api_url = (api_url or environ.get("FLOW_API_URL") or "https://sandbox.flow.cl/api").rstrip("/")
        self.timeout = timeout
        if not self.api_key or not self.secret_key:
            raise FlowConfigurationError("FLOW_API_KEY y FLOW_SECRET_KEY son obligatorias.")

    @staticmethod
    def signature_for(params, secret_key):
        normalized = {str(key): str(value) for key, value in params.items() if key != "s"}
        message = "".join(f"{key}{normalized[key]}" for key in sorted(normalized))
        return hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

    def sign(self, params):
        unsigned = {key: value for key, value in params.items() if key != "s"}
        return {**unsigned, "s": self.signature_for(unsigned, self.secret_key)}

    def verify_webhook_signature(self, params):
        received = str(params.get("s", ""))
        expected = self.signature_for(params, self.secret_key)
        return bool(received) and hmac.compare_digest(received.lower(), expected.lower())

    def create_payment(self, *, commerce_order, subject, amount, email, url_confirmation, url_return, optional=None, timeout=1800):
        params = {
            "apiKey": self.api_key,
            "commerceOrder": commerce_order,
            "subject": subject,
            "currency": "CLP",
            "amount": int(amount),
            "email": email,
            "urlConfirmation": url_confirmation,
            "urlReturn": url_return,
            "timeout": int(timeout),
        }
        if optional is not None:
            params["optional"] = json.dumps(optional, ensure_ascii=False, separators=(",", ":"))

        payload = self._post("/payment/create", self.sign(params))
        flow_order = payload.get("flowOrder")
        token = payload.get("token")
        checkout_base = payload.get("url")
        if flow_order is None or not token or not checkout_base:
            raise FlowAPIError("Flow devolvió una respuesta incompleta al crear la orden.", payload=payload)

        checkout_url = self._append_query(str(checkout_base), token=str(token))
        return FlowPaymentOrder(
            flow_order=str(flow_order),
            token=str(token),
            url=str(checkout_base),
            payment_url=checkout_url,
            raw=payload,
        )

    def get_status(self, token):
        params = self.sign({"apiKey": self.api_key, "token": str(token)})
        return self._get("/payment/getStatus", params)

    def _post(self, path, params):
        encoded = urlencode(params).encode("utf-8")
        request = Request(
            f"{self.api_url}{path}",
            data=encoded,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        return self._request_json(request)

    def _get(self, path, params):
        request = Request(
            f"{self.api_url}{path}?{urlencode(params)}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        return self._request_json(request)

    def _request_json(self, request):
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw[:1000]}
            raise FlowAPIError(
                f"Flow respondió HTTP {exc.code}.",
                status_code=exc.code,
                payload=payload,
            ) from exc
        except URLError as exc:
            raise FlowAPIError(f"No fue posible conectar con Flow: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise FlowAPIError("Flow devolvió JSON inválido.") from exc

    @staticmethod
    def _append_query(url, **params):
        parts = urlsplit(url)
        query = parts.query
        suffix = urlencode(params)
        query = f"{query}&{suffix}" if query else suffix
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


# Compatibilidad con imports previos; la implementación activa usa requests.
from payments.services.flow_client import FlowAPIError, FlowClient, FlowConfigurationError  # noqa: E402,F401
