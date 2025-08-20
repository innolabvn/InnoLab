from flask import Flask, render_template, request

app = Flask(__name__)

@app.route("/")
def home():
    """Renders the home page."""
    return render_template('index.html')

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    """Handles admin login."""
    error = None
    if request.method == "POST":
        admin_key = request.form.get('admin_key')
        if admin_key == "secure_admin_key":  # Replace "secure_admin_key" with a strong, securely stored key
            return render_template('administration.html')
        else:
            error = "Incorrect password"
    return render_template('admin_login.html', error=error)


if __name__ == "__main__":
    app.run(debug=True)