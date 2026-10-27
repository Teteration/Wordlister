import unittest

from wordlister_core.models import ExtractOptions
from wordlister_core.tokenizer import filter_words, is_opaque_value, is_sensitive_name, tokenize


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

    def test_counts_repeated_words_without_double_counting_identifier_parts(self) -> None:
        words = tokenize("account account resetPassword")

        self.assertEqual(2, words["account"])
        self.assertEqual(1, words["resetPassword"])
        self.assertEqual(1, words["reset"])
        self.assertEqual(1, words["Password"])

    def test_drops_persian_and_arabic_script_words(self) -> None:
        words = tokenize("account کاربر نام‌کاربری userکاربر endpoint")

        self.assertIn("account", words)
        self.assertIn("endpoint", words)
        self.assertNotIn("کاربر", words)
        self.assertNotIn("نام", words)
        self.assertNotIn("کاربری", words)
        self.assertNotIn("userکاربر", words)
        self.assertNotIn("user", words)

        filtered = filter_words(
            {"accountId", "شناسه", "userنام", "café", "v2"},
            ExtractOptions(character_filter="unicode"),
        )
        self.assertEqual({"accountId", "café", "v2"}, filtered)


if __name__ == "__main__":
    unittest.main()
