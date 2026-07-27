from django.test import SimpleTestCase
from .utils import check_input_letters, convert_title

class UtilsTest(SimpleTestCase):

    def test_convert_title_success(self):
        messy_text = "   jUAN   "
        clean_text = convert_title(messy_text)
        self.assertEqual(clean_text, "Juan")

    def test_convert_title_valid(self):
        result = convert_title("")
        self.assertEqual(result, "")
    
    def test_convert_title_valid_two(self):
        result = convert_title("Naruto Uzumaki")
        self.assertEqual(result, "Naruto Uzumaki")
    
    def test_check_input_letters_reject_emoji(self):
        result = check_input_letters("Juan 😊")
        self.assertFalse(result)
    
    def test_check_input_letters_reject_symbols(self):
        result = check_input_letters("Juan@Cruz!")
        self.assertFalse(result)
    
    def test_check_input_letters_too_long(self):
        long_name = "A" * 51
        result = check_input_letters(long_name)
        self.assertFalse(result)
    
    def test_convert_title_weird_capitalization(self):
        result = convert_title("dE la cRuz")
        self.assertEqual(result, "De La Cruz")
    
    def test_check_input_letter_only_space(self):
        result = check_input_letters("    ")
        self.assertTrue(result)

    # Test Perfectly valid name
    def test_check_input_letters_valid(self):
        result = check_input_letters("De La Cruz")
        self.assertTrue(result)

    #  Test a text with numbers
    def test_check_input_letters_invalid_number(self):
        result = check_input_letters("Juan123")
        self.assertFalse(result)
    
    def test_check_input_letters_blank(self):
        result = check_input_letters("")
        self.assertTrue(result)

    def test_check_input_letters_too_short(self):
        result = check_input_letters("Bo")
        self.assertFalse(result)

    def test_check_input_letters_tabs_and_newlines(self):
        result = check_input_letters("Juan\n\tCruz")
        self.assertTrue(result)
    
    def test_check_input_letters_sql_injection_attemts(self):
        result = check_input_letters("DROP TABLE user;")
        self.assertFalse(result)