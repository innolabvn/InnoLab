#!/usr/bin/env python3
"""
Test script for Gemini API integration
"""

import os
from dotenv import load_dotenv
import google.generativeai as genai

def test_gemini_api():
    """Test Gemini API connection and basic functionality"""
    
    # Load environment variables
    load_dotenv()
    
    # Get API key from environment
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        print("❌ GEMINI_API_KEY not found in environment variables")
        print("Please set GEMINI_API_KEY in your .env file")
        return False
    
    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)
        
        # Initialize the model (using newer model name)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Test with a simple prompt
        print("🤖 Testing Gemini API connection...")
        response = model.generate_content("Hello! Please respond with 'Gemini API is working correctly!'")
        
        print(f"✅ Success! Gemini response: {response.text}")
        return True
        
    except Exception as e:
        print(f"❌ Error testing Gemini API: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Starting Gemini API test...")
    success = test_gemini_api()
    
    if success:
        print("\n🎉 Gemini API is configured correctly!")
        print("You can now use Gemini for AI-powered code analysis and generation.")
    else:
        print("\n💡 To fix this:")
        print("1. Get your API key from: https://aistudio.google.com/apikey")
        print("2. Add it to your .env file: GEMINI_API_KEY=your_api_key_here")