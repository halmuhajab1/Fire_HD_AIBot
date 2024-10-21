import unittest             
from unittest.mock import patch, MagicMock        

# Mock data for the tests           
VIP_DATABASE = ["John Doe", "Jane Smith"]         

def InitializeBot():            
    # Simulated Initialization steps from the pseudocode      
    return {             
        "CLU_NLP_model": "loaded",          
        "Azure_server": "initialized",         
        "Ticketing_system": "connected",         
        "VIP_database": "loaded"          
    }               

def HandleIncomingCall(call):           
    # Simulated handling of an incoming call based on pseudocode logic    
    return "Ticket Generated”           

def IsVIP(name):             
    return name in VIP_DATABASE  # Check if the name is in the VIP database   

class TestBotFunctions(unittest.TestCase):        

    @patch('builtins.print')  # Patch print to avoid actual output    
    def test_initialize_bot(self, mock_print):        
        # Test InitializeBot function         
        result = InitializeBot()          
        self.assertEqual(result["CLU_NLP_model"], "loaded", "CLU NLP model failed to load")              
        self.assertEqual(result["Azure_server"], "initialized", "Azure server failed to initialize")            
        self.assertEqual(result["Ticketing_system"], "connected", "Ticketing system failed to connect")           
        self.assertEqual(result["VIP_database"], "loaded", "VIP database failed to load”)              

    @patch('builtins.input', side_effect=["John Doe", "High", "Phone", "1234567890", "john@example.com", "Office", "123 Main St", "Cannot log in"])   
    def test_handle_incoming_call_vip(self, mock_input):      
        # Simulate a VIP caller input         
        call = MagicMock()  # Mock the call object       
        result = HandleIncomingCall(call)         
        self.assertEqual(result, "Ticket Generated", "Failed to handle VIP call properly”)              

    def test_is_vip(self):           
        # Test VIP check for a known VIP         
        self.assertTrue(IsVIP("John Doe"), "VIP check failed for a known VIP")  
                      
        # Test VIP check for a non-VIP         
        self.assertFalse(IsVIP("Random Person"), "VIP check incorrectly passed for a non-VIP")             

    @patch('builtins.input', side_effect=["Random Person", "Medium", "Email", "random@example.com", "Home", "", "Printer not working"])      
    def test_handle_incoming_call_non_vip(self, mock_input):     
        # Simulate handling a non-VIP call        
        call = MagicMock()  # Mock the call object       
        result = HandleIncomingCall(call)         
        self.assertEqual(result, "Ticket Generated", "Failed to handle non-VIP call properly")             

if __name__ == '__main__':           
    unittest.main()            
