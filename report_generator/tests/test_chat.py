from unittest.mock import patch

from django.test import SimpleTestCase

from report_generator.intent import is_report_request
from tracker.ai.orchestrator import process_user_query


class IntentTests(SimpleTestCase):
    def test_report_requests(self):
        for msg in ('Generate a detailed report.', 'Create a PDF for this location.',
                    'Give me a business feasibility report.',
                    'Generate a comprehensive report with heatmap and revenue analysis.', 'Can you make me a pdf?'):
            self.assertTrue(is_report_request(msg), msg)

    def test_ordinary_questions_are_not_requests(self):
        for msg in ('What does the report include?', 'How do I generate a report?', 'Is the revenue report accurate?',
                    'show popular places', 'open cafe in Koramangala', ''):
            self.assertFalse(is_report_request(msg), msg)


class ChatbotIntegrationTests(SimpleTestCase):
    def test_request_with_selected_location_triggers_shared_flow(self):
        with patch('tracker.ai.orchestrator.gemini_analyze') as gemini:
            out = process_user_query('Generate a detailed report.',
                                     client_location_context={'lat': 12.97, 'lon': 77.59, 'name': 'MG Road'})
        gemini.assert_not_called()
        self.assertEqual(out['structured_actions'][0]['intent'], 'generate_report')
        self.assertTrue(out['structured_actions'][0]['auto_run'])
        self.assertIn('MG Road', out['message'])

    def test_request_without_location_asks_for_one(self):
        with patch('tracker.ai.orchestrator._geocode_place') as geocode, \
                patch('tracker.ai.orchestrator._build_trusted_location_context') as context:
            out = process_user_query('Create a PDF for this location.', client_location_context=None)
        geocode.assert_not_called()
        context.assert_not_called()  # never falls back to the default Bengaluru centre
        self.assertIn('no location is selected', out['message'])
        self.assertNotIn('generate_report', [a['intent'] for a in out['structured_actions']])

    def test_ordinary_question_goes_to_the_normal_assistant(self):
        with patch('tracker.ai.orchestrator._geocode_place', return_value=None), \
                patch('tracker.ai.orchestrator._build_trusted_location_context', return_value={'location': {}}), \
                patch('tracker.ai.orchestrator.gemini_analyze', return_value={'success': False, 'analysis': None}) as gemini, \
                patch('tracker.ai.orchestrator.grok_review', return_value={'success': False, 'review': None}):
            out = process_user_query('What does the report include for cafe in Indiranagar?',
                                     client_location_context={'lat': 12.97, 'lon': 77.59})
        gemini.assert_called_once()
        self.assertNotIn('generate_report', [a.get('intent') for a in out.get('structured_actions', [])])
