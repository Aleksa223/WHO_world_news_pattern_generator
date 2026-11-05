import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from economic_news_scripts import azure_translate, economic_news


class FakeResponse:
    def __init__(self, payload):
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self.body

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def saved_article(number, *, title, language, published_at=None):
    url = f"https://example.com/economy/{number}"
    return {
        "id": economic_news._article_id(url),
        "provider": "GDELT",
        "item_type": "article",
        "title": title,
        "description": None,
        "keywords": economic_news.DEFAULT_QUERY,
        "snippet": None,
        "url": url,
        "mobile_url": None,
        "image_url": None,
        "language": language,
        "published_at": published_at or f"2026-10-15T10:{number:02d}:00+00:00",
        "gdelt_seen_at": published_at or f"2026-10-15T10:{number:02d}:00+00:00",
        "gdelt_seen_date": f"20261015T10{number:02d}00Z",
        "source": "example.com",
        "source_country": "Exampleland",
        "feed": "gdelt_doc",
        "feed_rank": number,
        "query": economic_news.DEFAULT_QUERY,
        "category": "economic",
        "categories": ["economic"],
    }


def save_articles(database, articles, fetched_at="2026-10-15T11:00:00+00:00"):
    return economic_news.save_economic_news(
        database,
        {
            "query": economic_news.DEFAULT_QUERY,
            "fetched_at": fetched_at,
            "items": articles,
        },
    )


class AzureRequestTests(unittest.TestCase):
    @patch("economic_news_scripts.azure_translate.urlopen")
    def test_posts_canonical_text_objects_and_maps_detected_languages(
        self, mocked_urlopen
    ):
        mocked_urlopen.return_value = FakeResponse(
            [
                {
                    "detectedLanguage": {"language": "es", "score": 1.0},
                    "translations": [{"text": "Inflation falls", "to": "en"}],
                },
                {
                    "detectedLanguage": {"language": "ja", "score": 0.99},
                    "translations": [{"text": "GDP grows", "to": "en"}],
                },
            ]
        )

        result = azure_translate._request_translations(
            ["Baja la inflación", "GDPが成長"],
            key="super-secret-key",
            region="westeurope",
            endpoint=azure_translate.DEFAULT_ENDPOINT,
            timeout=17,
            retries=0,
        )

        request = mocked_urlopen.call_args.args[0]
        parsed_url = urlsplit(request.full_url)
        parameters = parse_qs(parsed_url.query)
        headers = {name.casefold(): value for name, value in request.header_items()}
        body = json.loads(request.data.decode("utf-8"))

        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(parsed_url.scheme, "https")
        self.assertEqual(parsed_url.netloc, "api.cognitive.microsofttranslator.com")
        self.assertEqual(parsed_url.path, "/translate")
        self.assertEqual(parameters, {"api-version": ["3.0"], "to": ["en"]})
        self.assertEqual(
            body,
            [{"Text": "Baja la inflación"}, {"Text": "GDPが成長"}],
        )
        self.assertEqual(
            headers["ocp-apim-subscription-key"], "super-secret-key"
        )
        self.assertEqual(headers["ocp-apim-subscription-region"], "westeurope")
        self.assertEqual(headers["content-type"], "application/json; charset=UTF-8")
        self.assertTrue(headers["x-clienttraceid"])
        self.assertEqual(mocked_urlopen.call_args.kwargs["timeout"], 17)
        self.assertEqual(
            result,
            [
                {"text": "Inflation falls", "source_language": "es"},
                {"text": "GDP grows", "source_language": "ja"},
            ],
        )

    @patch("economic_news_scripts.azure_translate.urlopen")
    def test_omits_region_header_when_region_is_not_configured(
        self, mocked_urlopen
    ):
        mocked_urlopen.return_value = FakeResponse(
            [
                {
                    "translations": [{"text": "Growth", "to": "en"}],
                }
            ]
        )

        result = azure_translate._request_translations(
            ["Croissance"],
            key="secret",
            region=None,
            endpoint="https://example.cognitiveservices.azure.com",
            timeout=5,
            retries=0,
        )

        request = mocked_urlopen.call_args.args[0]
        parsed_url = urlsplit(request.full_url)
        headers = {name.casefold(): value for name, value in request.header_items()}
        self.assertEqual(parsed_url.path, "/translator/text/v3.0/translate")
        self.assertNotIn("ocp-apim-subscription-region", headers)
        self.assertEqual(result, [{"text": "Growth", "source_language": None}])

    @patch("economic_news_scripts.azure_translate.urlopen")
    def test_http_error_reports_service_code_without_leaking_key(
        self, mocked_urlopen
    ):
        secret = "azure-key-that-must-not-leak"
        mocked_urlopen.side_effect = HTTPError(
            url="https://api.cognitive.microsofttranslator.com/translate",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(
                json.dumps(
                    {
                        "error": {
                            "code": 401000,
                            "message": f"Bad credential {secret}",
                        }
                    }
                ).encode("utf-8")
            ),
        )

        with self.assertRaises(azure_translate.AzureTranslationError) as context:
            azure_translate._request_translations(
                ["Inflación"],
                key=secret,
                region="westeurope",
                endpoint=azure_translate.DEFAULT_ENDPOINT,
                timeout=5,
                retries=0,
            )

        message = str(context.exception)
        self.assertIn("HTTP 401", message)
        self.assertIn("401000", message)
        self.assertNotIn(secret, message)
        self.assertNotIn("Bad credential", message)


class AzureDatabaseTests(unittest.TestCase):
    def test_missing_key_fails_before_network_or_database_access(self):
        with patch("economic_news_scripts.azure_translate.urlopen") as mocked_urlopen:
            with self.assertRaises(azure_translate.AzureTranslationError) as context:
                azure_translate.translate_database(
                    Path("does-not-exist.db"),
                    key="  ",
                )

        self.assertIn("AZURE_TRANSLATOR_KEY", str(context.exception))
        mocked_urlopen.assert_not_called()

    @patch("economic_news_scripts.azure_translate._request_translations")
    def test_batches_pending_titles_and_persists_english_fields(
        self, mocked_request
    ):
        foreign_articles = [
            saved_article(1, title="Inflación", language="Spanish"),
            saved_article(2, title="Wirtschaft", language="German"),
            saved_article(3, title="経済", language="Japanese"),
            saved_article(4, title="Безработица", language="Russian"),
            saved_article(5, title="Économie", language="French"),
        ]
        english_article = saved_article(
            6, title="Interest rates stay flat", language="English"
        )
        translations = {
            "Inflación": ("Inflation", "es"),
            "Wirtschaft": ("Economy", "de"),
            "経済": ("Economy", "ja"),
            "Безработица": ("Unemployment", "ru"),
            "Économie": ("Economy", "fr"),
        }

        def translated_batch(texts, **kwargs):
            return [
                {"text": translations[text][0], "source_language": translations[text][1]}
                for text in texts
            ]

        mocked_request.side_effect = translated_batch

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "economic_news.db"
            save_articles(database, foreign_articles + [english_article])

            result = azure_translate.translate_database(
                database,
                key="secret",
                region="westeurope",
                endpoint="https://translator.example.test",
                batch_size=2,
                timeout=9,
                retries=0,
            )

            with closing(sqlite3.connect(database)) as connection:
                columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(economic_articles)"
                    )
                }
                staged_columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(stg_economic_articles)"
                    )
                }
                rows = {
                    row[0]: row[1:]
                    for row in connection.execute(
                        """
                        SELECT
                            title_original,
                            title,
                            title_english,
                            translation_source_language,
                            translation_status,
                            translation_provider,
                            translated_at
                        FROM economic_articles
                        """
                    )
                }

        self.assertEqual(result, {"selected": 5, "translated": 5, "stale": 0})
        self.assertEqual(mocked_request.call_count, 3)
        batch_lengths = [len(invocation.args[0]) for invocation in mocked_request.call_args_list]
        self.assertEqual(batch_lengths, [2, 2, 1])
        for invocation in mocked_request.call_args_list:
            self.assertEqual(invocation.kwargs["key"], "secret")
            self.assertEqual(invocation.kwargs["region"], "westeurope")
            self.assertEqual(
                invocation.kwargs["endpoint"], "https://translator.example.test"
            )
            self.assertEqual(invocation.kwargs["timeout"], 9)
            self.assertEqual(invocation.kwargs["retries"], 0)

        translation_columns = {
            "title_original",
            "title_english",
            "translation_source_language",
            "translation_status",
            "translation_provider",
            "translated_at",
        }
        self.assertTrue(translation_columns <= columns)
        self.assertTrue(translation_columns <= staged_columns)
        for article in foreign_articles:
            original = article["title"]
            expected_english, expected_language = translations[original]
            row = rows[original]
            self.assertEqual(row[0], expected_english)
            self.assertEqual(row[1], expected_english)
            self.assertEqual(row[2], expected_language)
            self.assertEqual(row[3], "translated")
            self.assertEqual(row[4], azure_translate.AZURE_TRANSLATOR_PROVIDER)
            self.assertIsNotNone(row[5])

        english_row = rows[english_article["title"]]
        self.assertEqual(english_row[0], english_article["title"])
        self.assertEqual(english_row[1], english_article["title"])
        self.assertEqual(english_row[2], "en")
        self.assertEqual(english_row[3], "original_english")
        self.assertEqual(english_row[4], "source")
        self.assertIsNone(english_row[5])

    def test_refetch_preserves_translation_until_original_title_changes(self):
        article = saved_article(1, title="Inflación", language="Spanish")

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "economic_news.db"
            save_articles(database, [article])
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute(
                    """
                    UPDATE economic_articles
                    SET
                        title = 'Inflation',
                        title_english = 'Inflation',
                        translation_source_language = 'es',
                        translation_status = 'translated',
                        translation_provider = 'Azure Translator',
                        translated_at = '2026-10-15T12:00:00+00:00'
                    """
                )

            save_articles(
                database,
                [article],
                fetched_at="2026-10-15T13:00:00+00:00",
            )
            with closing(sqlite3.connect(database)) as connection:
                preserved = connection.execute(
                    """
                    SELECT
                        title, title_original, title_english,
                        translation_source_language, translation_status,
                        translation_provider, translated_at
                    FROM economic_articles
                    """
                ).fetchone()

            changed = {**article, "title": "La inflación vuelve a subir"}
            save_articles(
                database,
                [changed],
                fetched_at="2026-10-15T14:00:00+00:00",
            )
            with closing(sqlite3.connect(database)) as connection:
                reset = connection.execute(
                    """
                    SELECT
                        title, title_original, title_english,
                        translation_source_language, translation_status,
                        translation_provider, translated_at
                    FROM economic_articles
                    """
                ).fetchone()

        self.assertEqual(
            preserved,
            (
                "Inflation",
                "Inflación",
                "Inflation",
                "es",
                "translated",
                "Azure Translator",
                "2026-10-15T12:00:00+00:00",
            ),
        )
        self.assertEqual(
            reset,
            (
                "La inflación vuelve a subir",
                "La inflación vuelve a subir",
                None,
                None,
                "pending",
                None,
                None,
            ),
        )

    @patch("economic_news_scripts.azure_translate.translate_database")
    def test_environment_wrapper_passes_credentials_without_persisting_them(
        self, mocked_translate
    ):
        mocked_translate.return_value = {"selected": 0, "translated": 0, "stale": 0}
        database = Path("economic_articles/economic_news.db")

        with patch.dict(
            os.environ,
            {
                "AZURE_TRANSLATOR_KEY": "environment-secret",
                "AZURE_TRANSLATOR_REGION": "northeurope",
                "AZURE_TRANSLATOR_ENDPOINT": "https://translator.example.test",
            },
            clear=True,
        ):
            result = azure_translate.translate_database_from_environment(
                database,
                batch_size=7,
                limit=11,
                timeout=13,
            )

        self.assertEqual(result, {"selected": 0, "translated": 0, "stale": 0})
        mocked_translate.assert_called_once_with(
            database,
            key="environment-secret",
            region="northeurope",
            endpoint="https://translator.example.test",
            batch_size=7,
            limit=11,
            timeout=13,
        )


class AzureCliIntegrationTests(unittest.TestCase):
    @patch("economic_news_scripts.economic_news._write_json")
    @patch("economic_news_scripts.economic_news._translate_saved_titles")
    @patch("economic_news_scripts.economic_news.save_economic_news")
    @patch("economic_news_scripts.economic_news.fetch_economic_news")
    def test_economic_news_translate_flag_runs_after_database_save(
        self,
        mocked_fetch,
        mocked_save,
        mocked_translate,
        mocked_write,
    ):
        mocked_fetch.return_value = {
            "count": 1,
            "available": 1,
            "skipped": 0,
            "items": [saved_article(1, title="Inflación", language="Spanish")],
        }
        mocked_save.return_value = {
            "inserted": 1,
            "updated": 0,
            "total": 1,
            "staged": 1,
        }
        mocked_translate.return_value = {"selected": 1, "translated": 1, "stale": 0}
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test-economic.db"
            with redirect_stderr(stderr):
                result = economic_news.main(
                    [
                        "--translate",
                        "--database",
                        str(database),
                        "--timeout",
                        "19",
                    ]
                )

        self.assertEqual(result, 0)
        mocked_save.assert_called_once()
        mocked_translate.assert_called_once_with(database, 19)
        mocked_write.assert_called_once()
        self.assertIn("Azure Translator: 1 titles translated", stderr.getvalue())

    def test_translator_cli_reports_missing_key_without_printing_a_secret(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(stderr):
            result = azure_translate.main(
                ["--database", "economic_articles/does-not-exist.db"]
            )

        self.assertEqual(result, 1)
        self.assertIn("AZURE_TRANSLATOR_KEY", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
