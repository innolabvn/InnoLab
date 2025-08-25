from flask import Flask, render_template , request

app = Flask(__name__)

@app.route("/")
def home():
    return render_template('index.html')

# this is the function for the admin backdoor access:
@app.route("/sl", methods=["GET","POST"])
def adm_log_sec():

    # Remove the admin backdoor route entirely for security reasons
    return "Unauthorized Access", 403

# implement login process to the app



# the main function this is going to execute like any other main function
if __name__ == "__main__":
    app.run(debug=True)