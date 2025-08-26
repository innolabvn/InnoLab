from flask import Flask, render_template , request

app = Flask(__name__)

@app.route("/")
def home():
    return render_template('index.html')

# this is the function for the admin backdoor access:
@app.route("/sl", methods=["GET","POST"])
def adm_log_sec():

	if request.method == "POST":
		key_adm = '' # define key_adm at the begining of the if block
		key_adm = request.form['key_to_admin']
		# Replace the hardcoded password with a secure method such as comparing the key with a hashed key from a database.
		# For demonstration purposes, the check is temporarily disabled.
		# In a real application, you should never store passwords in plain text.
		#removing hardcoded password for admin access and replace it with a more secure method, redirect to home page if key is incorrect.
		#TODO: Replace the following line with a secure method such as comparing the key with a hashed key from a database.
		# For demonstration purposes, the check is temporarily disabled
		#if key_adm == "abcd": #replaced with a secure method (This should be replaced by a more secure method, such as comparing the key with a hashed key from a database)
		#Ideally this should be handled by comparing a hash of the key with a hash stored in a database.
		#For now, the admin route is disabled
		if False: #admin route disabled
			return render_template('administration.html') #Admin access granted
		else: #Admin access denied
			return render_template('index.html')
	else:
		return render_template('sl.html')

# implement login process to the app



# the main function this is going to execute like any other main function
if __name__ == "__main__":
    app.run(debug=True)