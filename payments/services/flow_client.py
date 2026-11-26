import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class FlowConfigurationError(RuntimeError):
    pass


class FlowAPIError(RuntimeError):
    def __init__(self, message, *, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class FlowClient:
    def __init__(self, api_key=None, secret_key=None, api_url=None, timeout=30):
        self.api_key = api_key if api_key is not None else settings.FLOW_API_KEY
        self.secret_key = secret_key if secret_key is not None else settings.FLOW_SECRET_KEY
        self.api_url = (api_url if api_url is not None else settings.FLOW_API_URL).rstrip("/")
        self.timeout = timeout
        if not self.api_key or not self.secret_key:
            raise FlowConfigurationError("FLOW_API_KEY y FLOW_SECRET_KEY son obligatorias.")

    @staticmethod
    def signature_for(params, secret_key):
        normalized = {str(key): str(value) for key, value in params.items() if key != "s"}
        to_sign = "".join(f"{key}{normalized[key]}" for key in sorted(normalized))
        return hmac.new(secret_key.encode("utf-8"), to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    def _sign(self, params):
        unsigned = {key: value for key, value in params.items() if key != "s"}
        return {**unsigned, "s": self.signature_for(unsigned, self.secret_key)}

    def verify_webhook_signature(self, params):
        received = str(params.get("s", ""))
        expected = self.signature_for(params, self.secret_key)
        return bool(received) and hmac.compare_digest(received.lower(), expected.lower())

    def create_payment(
        self,
        commerce_order,
        subject,
        amount,
        email,
        url_confirmation,
        url_return,
        timeout=None,
        optional=None,
    ):
        params = {
            "apiKey": self.api_key,
            "commerceOrder": str(commerce_order),
            "subject": str(subject),
            "currency": "CLP",
            "amount": int(amount),
            "email": str(email),
            "urlConfirmation": str(url_confirmation),
            "urlReturn": str(url_return),
        }
        if timeout is not None:
            params["timeout"] = int(timeout)
        if optional is not None:
            params["optional"] = json.dumps(optional, ensure_ascii=False, separators=(",", ":"))

        data = self._post("/payment/create", self._sign(params))
        required = ("flowOrder", "url", "token")
        if any(not data.get(key) for key in required):
            raise FlowAPIError("Flow devolvió una respuesta incompleta.", payload=data)
        return {
            "flow_order": str(data["flowOrder"]),
            "token": str(data["token"]),
            "payment_url": f"{data['url']}?token={data['token']}",
            "raw": data,
        }

    def get_status(self, token):
        params = self._sign({"apiKey": self.api_key, "token": str(token)})
        return self._get("/payment/getStatus", params)

    def _post(self, path, params):
        return self._request("POST", path, data=params)

    def _get(self, path, params):
        return self._request("GET", path, params=params)

    def _request(self, method, path, **kwargs):
        url = f"{self.api_url}{path}"
        try:
            response = requests.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            logger.warning("Flow timeout in %s %s", method, path)
            raise FlowAPIError("Flow no respondió a tiempo.") from exc
        except requests.RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            payload = None
            if getattr(exc, "response", None) is not None:
                try:
                    payload = exc.response.json()
                except ValueError:
                    payload = None
            logger.warning("Flow request failed: method=%s path=%s status=%s", method, path, status_code)
            raise FlowAPIError("Flow rechazó la solicitud.", status_code=status_code, payload=payload) from exc
        except ValueError as exc:
            raise FlowAPIError("Flow devolvió una respuesta no válida.") from exc
