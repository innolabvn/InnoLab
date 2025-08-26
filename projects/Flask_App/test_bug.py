# Test file with intentional bugs for testing fix functionality

def bad_function():
    # Bug 1: Hardcoded password
    password = "SECURE_PASSWORD_REPLACE_ME"  # Replace with secure password handling - for demonstration only: Fixed hardcoded password

    # Bug 2: SQL injection vulnerability
    query = "SELECT * FROM users WHERE name = %s"  # Replace with parameterized query: Fixed SQL injection vulnerability - changed to parameterized query

    # Bug 3: Division by zero potential
    denominator = 1
    result = 10 / denominator if denominator else 0  # Handle potential division by zero : Added check to prevent division by zero

    # Bug 4: Unused variable
    # unused_var = "this is not used" : Removed unused variable
    
    return result

if __name__ == "__main__":
    bad_function()