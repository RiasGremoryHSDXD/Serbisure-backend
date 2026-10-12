import json
from unittest.mock import MagicMock, patch
import requests
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from .sentiment import analyze_feedback, SentimentUnavailable


@override_settings(HUGGINGFACE_API_TOKEN='private-test-token',
                   HUGGINGFACE_SENTIMENT_SPACE_URL='https://example.hf.space',
                   HUGGINGFACE_SENTIMENT_MODEL_ID='Rhoii/cebuano-taglish-sentiment',
                   HUGGINGFACE_SENTIMENT_TIMEOUT_SECONDS=30)
class SentimentTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.payload = [{'label': 'Negative', 'confidences': None}, .7271,
                        {'Negative': .7271, 'Positive': .1981, 'Neutral': .0748}]
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        post = self.session.post.return_value.__enter__.return_value
        post.status_code = 200
        post.json.return_value = {'event_id': 'a' * 32}
        self.stream = self.session.get.return_value.__enter__.return_value
        self.stream.status_code = 200
        self.factory = patch('reviews.sentiment.requests.Session', return_value=self.session).start()
        self.addCleanup(patch.stopall)

    def complete(self, payload=None):
        self.stream.iter_lines.return_value = [
            'event: heartbeat', 'data: null', '',
            'event: complete', 'data: ' + json.dumps(self.payload if payload is None else payload), '',
        ]

    def test_authenticated_gradio_handshake_and_real_result(self):
        self.complete()
        result = analyze_feedback('Dili kabalo mo lipyo')
        self.assertEqual(result['label'], 'Negative')
        self.assertEqual(result['confidence'], .7271)
        self.assertEqual(result['probabilities'], self.payload[2])
        self.assertEqual(result['source'], 'huggingface')
        for call in (self.session.post.call_args, self.session.get.call_args):
            self.assertEqual(call.kwargs['headers']['Authorization'], 'Bearer private-test-token')
            self.assertFalse(call.kwargs['allow_redirects'])
        self.assertEqual(self.session.post.call_args.kwargs['json'], {'data': ['Dili kabalo mo lipyo']})
        self.assertEqual(analyze_feedback('Dili kabalo mo lipyo'), result)
        self.session.post.assert_called_once()

    def test_error_event_with_http_200_is_not_neutral(self):
        self.stream.iter_lines.return_value = ['event: error', 'data: {"error":"quota exceeded"}', '']
        with self.assertRaises(SentimentUnavailable) as error:
            analyze_feedback('Pangit ug batasan')
        self.assertEqual(error.exception.reason, 'provider_error_event')

    def test_invalid_or_inconsistent_output_is_rejected(self):
        for payload in ([{'label': 'LABEL_0'}, .9, self.payload[2]],
                        [{'label': 'Positive'}, .7271, self.payload[2]],
                        [{'label': 'Negative'}, float('nan'), self.payload[2]],
                        [{'label': 'Negative'}, .7271, {'Negative': .7271}], [None]):
            with self.subTest(payload=payload):
                self.complete(payload)
                with self.assertRaises(SentimentUnavailable):
                    analyze_feedback('Pangit ug batasan')

    def test_missing_token_and_untrusted_destination_fail_closed(self):
        for settings in ({'HUGGINGFACE_API_TOKEN': ''},
                         {'HUGGINGFACE_SENTIMENT_SPACE_URL': 'http://example.hf.space'},
                         {'HUGGINGFACE_SENTIMENT_SPACE_URL': 'https://example.org'}):
            with self.subTest(settings=settings), override_settings(**settings):
                with self.assertRaises(SentimentUnavailable):
                    analyze_feedback('Pangit ug batasan')
        self.session.post.assert_not_called()

    def test_network_exception_does_not_expose_private_token(self):
        self.session.post.side_effect = requests.ConnectionError('private-test-token')
        with self.assertLogs('reviews.sentiment', level='WARNING') as logs:
            with self.assertRaises(SentimentUnavailable) as error:
                analyze_feedback('Pangit ug batasan')
        self.assertNotIn('private-test-token', str(error.exception))
        self.assertNotIn('private-test-token', str(logs.output))

    def test_incomplete_stream_and_http_failure_are_not_predictions(self):
        self.stream.iter_lines.return_value = ['event: heartbeat', 'data: null', '']
        with self.assertRaises(SentimentUnavailable):
            analyze_feedback('Pangit ug batasan')
        self.stream.status_code = 503
        with self.assertRaises(SentimentUnavailable):
            analyze_feedback('Pangit ug batasan')
