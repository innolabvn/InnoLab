from flask import Flask, render_template , request

app = Flask(__name__)

@app.route("/")
def home():
    return render_template('index.html')

# Remove the admin backdoor route entirely for security reasons
# implement login process to the app

# the main function this is going to execute like any other main function
if __name__ == "__main__":
    app.run(debug=False) # Fix: Disable debug mode in production for security and performance reasons. Debug mode should only be enabled during development.