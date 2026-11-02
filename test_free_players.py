import unittest
from unittest.mock import patch, Mock
from free_players import parse_team_roster, fetch_team_roster, RosterUnavailable

class TestRosters(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_team_roster({'squad':[{'name':'Test Player','position':'Midfield','nationality':'Spain'}]})[0]['Name'], 'Test Player')
    def test_empty(self):
        self.assertEqual(parse_team_roster({'squad':None}), [])
    @patch('free_players.requests.get')
    def test_request(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {'squad':[{'name':'Example'}]}
        self.assertEqual(fetch_team_roster(86, 'fake')[0]['Name'], 'Example')
        self.assertTrue(get.call_args.kwargs['headers']['X-Auth-Token'] == 'fake')
    @patch('free_players.requests.get')
    def test_rejected(self, get):
        get.return_value.status_code = 403
        with self.assertRaises(RosterUnavailable): fetch_team_roster(86, 'fake')

if __name__ == '__main__': unittest.main()
