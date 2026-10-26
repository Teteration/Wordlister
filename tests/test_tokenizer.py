import unittest

from wordlister_core.tokenizer import is_opaque_value, is_sensitive_name, tokenize


class TokenizerTests(unittest.TestCase):
    def test_preserves_identifiers_and_adds_useful_components(self) -> None:
        words = tokenize("GetHTTPResponse user_profile payment-confirmation apiV2")

        self.assertTrue(
            {
                "GetHTTPResponse",
                "Get",
                "HTTP",
                "Response",
                "user_profile",
                "user",
                "profile",
                "payment-confirmation",
                "payment",
                "confirmation",
                "apiV2",
                "api",
                "V2",
            }.issubset(words)
        )

    def test_recognizes_sensitive_context_names_without_false_positive(self) -> None:
        self.assertTrue(is_sensitive_name("access_token"))
        self.assertTrue(is_sensitive_name("clientSecret"))
        self.assertTrue(is_sensitive_name("csrf-token"))
        self.assertFalse(is_sensitive_name("tokenizer"))
        self.assertFalse(is_sensitive_name("sessionReport"))

    def test_recognizes_common_opaque_secret_shapes(self) -> None:
        self.assertTrue(
            is_opaque_value("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue")
        )
        self.assertTrue(is_opaque_value("-----BEGIN PRIVATE KEY-----"))
        self.assertFalse(is_opaque_value("resetPasswordEndpoint"))


if __name__ == "__main__":
    unittest.main()
