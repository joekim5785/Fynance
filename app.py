import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///fynance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # get the required data
    portfolios = db.execute(
        "SELECT symbol,shares,stock_price,total FROM purchases WHERE user_id = ?", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    # get the current share prices

    for portfolio in portfolios:
        stock = lookup(portfolio["symbol"])
        portfolio["stock_price"] = stock["price"]
        portfolio["total"] = round(portfolio["shares"] * stock["price"], 2)

    total = 0

    for portfolio in portfolios:
        total += portfolio["total"]

    total_balance = round(total + cash, 2)

    return render_template(
        "index.html",
        cash=cash,
        total_balance=total_balance,
        portfolios=portfolios
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    else:
        symbol = request.form.get("symbol").strip().upper()
        stock = lookup(symbol)

        shares = request.form.get("shares")

        if not request.form.get("symbol"):
            return apology("Input symbol", 400)
        elif stock is None:
            return apology("Invalid symbol", 400)
        elif not shares:
            return apology("Input shares", 400)

        elif not shares.isdigit():
            return apology("shares must be a positive integer", 400)
        shares = int(shares)
        if shares < 1:
            return apology("shares shares", 400)

        # check if the user has enough cash for the purchase
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = cash[0]["cash"]
        # total cost of purchase
        total = shares * stock["price"]
        if total > cash:
            return apology("Your balance is curently low to complete the transaction", 400)

        # record purchase in database
        company_name = stock["name"]
        stock_price = stock["price"]
        purchase_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # check whether the user already owns the share
        existing = db.execute(
            "SELECT shares FROM purchases WHERE user_id = ? AND symbol = ?",
            session["user_id"],
            symbol
        )

        # if the user already owns
        if existing:
            db.execute(
                """
          UPDATE purchases
         SET shares = shares + ?, stock_price = ?
          WHERE user_id = ? AND symbol = ?
         """,
                shares,
                stock_price,
                session["user_id"],
                symbol
            )
        else:
            db.execute(
                """
            INSERT INTO purchases
            (user_id, company_name, symbol, shares, stock_price, purchase_time, total)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                session["user_id"],
                company_name,
                symbol,
                shares,
                stock_price,
                purchase_time,
                total
            )
        # update balance
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total, session["user_id"])

        # record transation
        db.execute(
            """
        INSERT INTO transactions
        (user_id, symbol, shares, price, transaction_type,transaction_time)
        VALUES (?, ?, ?, ?, ?,?)
        """,
            session["user_id"],
            symbol,
            shares,
            stock_price,
            "BUY",
            purchase_time
        )

        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute(
        """
        SELECT symbol,
            shares,
            price,
            transaction_type,
            transaction_time
        FROM transactions
        WHERE user_id = ?
        ORDER BY transaction_time DESC
        """,
        session["user_id"]
    )
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # request method is get
    if request.method == "GET":
        return render_template("quote.html")

    else:
        symbol = request.form.get("symbol")
        stock = lookup(symbol)
        if not symbol:
            return apology("must provide symbol", 400)
        elif stock is None:
            return apology("Invalid symbol", 400)

        return render_template("quoted.html", stock=stock)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")

    # get the name
    username = request.form.get("username")
    # get the password
    password = request.form.get("password")
    # get confirmation password
    confirmation = request.form.get("confirmation")

    if not username:
        return apology("must provide username", 400)

    existing = db.execute("SELECT username FROM users WHERE username = ?", username)
    if len(existing) > 0:
        return apology("username already exists", 400)

    # Ensure password was submitted

    elif not password:
        return apology("must provide password", 400)
    # ensure user confirms the password

    elif not confirmation:
        return apology("must confirm password", 400)
    # Both password match
    elif password != confirmation:
        return apology("Passwords Do Not Match! Try Again!", 400)
    else:
        # hash the password before storing it to the database
        hashed_password = generate_password_hash(password)
        # insert values into the database
        user_id = db.execute("INSERT INTO users(username,hash) VALUES (?,?)",
                             username, hashed_password)
        # redirect to log user in
        session["user_id"] = user_id
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_stocks = db.execute(
        "SELECT symbol,shares FROM purchases  WHERE user_id = ?", session["user_id"])
    sale_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if request.method == "GET":
        return render_template("sell.html", user_stocks=user_stocks)
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("Input the stock symbol", 400)
        elif not shares:
            return apology("Input shares", 403)
        shares = int(shares)
        if shares > user_stocks[0]["shares"]:
            return apology("too many shares", 400)
        if int(shares) < 1:
            return apology("Input more than one share", 400)
        user_stocks = db.execute(
            "SELECT shares FROM purchases WHERE user_id = ? AND symbol = ?",
            session["user_id"],
            symbol
        )
        if len(user_stocks) == 0:
            return apology("You don't own these shares", 400)
        stock = lookup(symbol)
        if stock is None:
            return apology("Invalid symbol", 403)
        # execute sale
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        cash = cash[0]["cash"]
        current_stock_price = stock["price"]
        sales = shares * current_stock_price

        # update the shares
        if shares == user_stocks:
            # delete the shares  when the number of shares sold and shares owned are of the same amount
            db.execute("DELETE FROM purchases WHERE user_id = ? AND symbol = ?",
                       session["user_id"], symbol)
        else:
            db.execute(
                "UPDATE purchases SET shares = shares - ? WHERE user_id = ? AND symbol = ?",
                shares,
                session["user_id"],
                symbol
            )

        # update the cash
        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?",
            sales,
            session["user_id"]
        )
        # Update transaction
        db.execute(
            """
        INSERT INTO transactions
        (user_id, symbol, shares, price, transaction_type,transaction_time)
        VALUES (?, ?, ?, ?, ?,?)
        """,
            session["user_id"],
            symbol,
            shares,
            current_stock_price,
            "SELL",
            sale_time
        )
        return redirect("/")


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        # ensure that there's input
        if not current_password:
            return apology("must provide current_password", 400)
        elif not new_password:
            return apology("must provide new password", 400)
        elif not confirm_password:
            return apology("must confirm the new password", 400)

        # confirm if the user's current password is similar to the one typed
        stored_hash = db.execute("SELECT hash FROM users WHERE id= ?",
                                 session["user_id"])[0]["hash"]

        if not check_password_hash(stored_hash, current_password):
            return apology("Wrong current password", 400)
        elif check_password_hash(stored_hash, new_password):
            return apology("Enter a different  password", 400)
        elif new_password != confirm_password:
            return apology("Confirmed password don't match", 400)

        # update the password in the database
        hashed_new_password = generate_password_hash(new_password)
        db.execute("UPDATE users SET hash = ? WHERE id = ?",
                   hashed_new_password, session["user_id"])

        return redirect("/")

    else:
        return render_template("profile.html")


#deposit money into account
@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        amount = request.form.get("amount")
        if not amount:
            return apology("must provide amount", 400)
        elif float(amount) < 1:
            return apology("amount must be greater than 0", 400)

        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", float(amount), session["user_id"])
        return redirect("/")

    else:
        return render_template("deposit.html")