import unittest             
from ticket_handler import format_ticket        

class TestFormatTicket(unittest.TestCase):        

    def test_format_ticket_office_location(self):      
        # Arrange            
        user_info = {            
            "name": "John Doe",          
            "contactMethod": "Phone",         
            "phoneNumber": "123-456-7890",        
            "email": "johndoe@example.com",        
            "workLocation": "Office",         
            "workAddress": "123 Office St.",       
            "priority": "High",          
            "issueDescription": "Computer won't start"      
        }              

        # Act             
        ticket = format_ticket(user_info)        

        # Assert             
        expected_ticket = ("Name: John Doe\n"       
                           "Best Contact Method: Phone\n"     
                           "Phone Number: 123-456-7890\n"     
                           "Email: johndoe@example.com\n"     
                           "Work Location: Office\n"      
                           "Work Address: 123 Office St.\n"     
                           "Urgency: High\n"       
                           "Issue Description: Computer won't start\n")  
        self.assertEqual(ticket, expected_ticket)      

    def test_format_ticket_remote_location(self):      
        # Arrange            
        user_info = {            
            "name": "Jane Doe",          
            "contactMethod": "Email",         
            "phoneNumber": "098-765-4321",        
            "email": "janedoe@example.com",        
            "workLocation": "Remote",         
            "priority": "Medium",         
            "issueDescription": "VPN not working"      
        }              
        # Act             
        ticket = format_ticket(user_info)        

        # Assert             
        expected_ticket = ("Name: Jane Doe\n"       
                           "Best Contact Method: Email\n"     
                           "Phone Number: 098-765-4321\n"     
                           "Email: janedoe@example.com\n"     
                           "Work Location: Remote\n"      
                           "Urgency: Medium\n"       
                           "Issue Description: VPN not working\n")   
        self.assertEqual(ticket, expected_ticket)      

if __name__ == '__main__':           
    unittest.main()            
