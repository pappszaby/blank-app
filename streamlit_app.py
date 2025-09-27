import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import altair as alt
from datetime import date
import random
import string

DB = "expenses.db"

# --- Initialize DB1 ---
def init_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY,
            date TEXT,
            category TEXT,
            amount REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            reset_code TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()

# --- Helper functions ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    return hash_password(password) == password_hash

def generate_reset_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# --- Init Session State ---
for key, default in {
    'logged_in': False,
    'username': '',
    'show_reset': False,
    'show_register': False,
    'rerun_flag': False
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- Auth Functions ---
def login():
    st.title("Bejelentkezés")
    st.header("Nádasdy utca 15/1 (411-es lakás)")
    username = st.text_input("Felhasználónév")
    password = st.text_input("Jelszó", type="password")

    if st.button("Bejelentkezés"):
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and verify_password(password, user[2]):
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.session_state['rerun_flag'] = not st.session_state['rerun_flag']  # Force rerun workaround
            st.success(f"Sikeres bejelentkezés, üdv {username}!")
        else:
            st.error("Hibás felhasználónév vagy jelszó")

    if st.button("Új jelszó kérése"):
        st.session_state['show_reset'] = True

def register():
    st.title("Regisztráció")
    new_user = st.text_input("Új felhasználónév")
    new_pass = st.text_input("Új jelszó", type="password")
    confirm_pass = st.text_input("Jelszó megerősítése", type="password")

    if st.button("Regisztráció"):
        if not new_user or not new_pass:
            st.error("Töltsd ki az összes mezőt!")
        elif new_pass != confirm_pass:
            st.error("A jelszavak nem egyeznek!")
        else:
            existing = conn.execute("SELECT * FROM users WHERE username = ?", (new_user,)).fetchone()
            if existing:
                st.error("Ez a felhasználónév már foglalt.")
            else:
                pw_hash = hash_password(new_pass)
                conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (new_user, pw_hash))
                conn.commit()
                st.success("Sikeres regisztráció! Jelentkezz be.")
                st.session_state['show_register'] = False

def reset_password():
    st.title("Jelszó visszaállítás")
    username = st.text_input("Felhasználónév a visszaállításhoz")

    if st.button("Reset kód kérése"):
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user:
            code = generate_reset_code()
            conn.execute("UPDATE users SET reset_code = ? WHERE username = ?", (code, username))
            conn.commit()
            st.success(f"Visszaállító kód generálva: {code}")
        else:
            st.error("Nincs ilyen felhasználó")

    st.divider()
    code_input = st.text_input("Reset kód")
    new_pass = st.text_input("Új jelszó", type="password")
    confirm_pass = st.text_input("Jelszó megerősítése", type="password")

    if st.button("Jelszó módosítása"):
        user = conn.execute("SELECT * FROM users WHERE reset_code = ?", (code_input,)).fetchone()
        if user:
            if new_pass != confirm_pass:
                st.error("A jelszavak nem egyeznek!")
            else:
                pw_hash = hash_password(new_pass)
                conn.execute("UPDATE users SET password_hash = ?, reset_code = NULL WHERE id = ?", (pw_hash, user[0]))
                conn.commit()
                st.success("Sikeres jelszócsere! Jelentkezz be.")
                st.session_state['show_reset'] = False
        else:
            st.error("Érvénytelen kód.")

# --- Expense Tracker ---
def expense_app():
    st.title(f" Üdv! – {st.session_state['username']}")
    st.header(f"Nádasdy utca 15/1 411-es lakás (albérlő költségei)")

    categories = [
        "Lakbér", "Közös költség", "Áram", "Hideg víz",
        "Meleg víz", "Fűtés", "Internet_TV", "Egyéb"
    ]

    with st.form("add_expense"):
        d = st.date_input("Dátum", value=date.today())
        cat = st.selectbox("Kategória", categories)
        amt = st.number_input("Összeg (Ft)", min_value=0.0, format="%.2f")
        submitted = st.form_submit_button("Hozzáadás")
        if submitted:
            conn.execute("INSERT INTO expenses (date, category, amount) VALUES (?, ?, ?)", (d.isoformat(), cat, float(amt)))
            conn.commit()
            st.success("Kiadás hozzáadva.")

    month = st.text_input("Hónap (ÉÉÉÉ-HH)", value=date.today().strftime("%Y-%m"))

    if st.button("Havi összesítés"):
        df = pd.read_sql_query("SELECT date, category, amount FROM expenses WHERE date LIKE ? ORDER BY date DESC", conn, params=(month + "%",))
        total = df['amount'].sum() if not df.empty else 0.0
        st.write(f"Összesen: {total:.2f} Ft")
        st.dataframe(df)

    if st.button("Összes kiadás"):
        df_all = pd.read_sql_query("SELECT id, date, category, amount FROM expenses ORDER BY date DESC", conn)
        st.dataframe(df_all)
        st.write(f"Teljes összeg: {df_all['amount'].sum():.2f} Ft")

        df_all['month'] = pd.to_datetime(df_all['date']).dt.to_period('M').astype(str)
        monthly = df_all.groupby('month')['amount'].sum().reset_index()
        st.write("Havi bontás:")
        st.dataframe(monthly)

    if st.button("Kategória diagram"):
        df = pd.read_sql_query("SELECT category, SUM(amount) as total FROM expenses WHERE date LIKE ? GROUP BY category", conn, params=(month + "%",))
        if df.empty:
            st.info("Nincs adat.")
        else:
            chart = alt.Chart(df).mark_arc().encode(
                theta="total:Q",
                color="category:N",
                tooltip=["category:N", "total:Q"]
            )
            st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.subheader("Kiadások szerkesztése / törlése")

    df_edit = pd.read_sql_query("SELECT * FROM expenses ORDER BY date DESC", conn)
    df_edited = st.data_editor(df_edit, use_container_width=True, num_rows="dynamic")

    if st.button("Módosítások mentése"):
        for i in range(len(df_edited)):
            row = df_edited.iloc[i]
            conn.execute("UPDATE expenses SET date=?, category=?, amount=? WHERE id=?", (row['date'], row['category'], row['amount'], row['id']))
        conn.commit()
        st.success("Módosítások elmentve.")

    del_id = st.number_input("Törlendő ID", min_value=1, step=1)
    if st.button("Törlés"):
        conn.execute("DELETE FROM expenses WHERE id = ?", (del_id,))
        conn.commit()
        st.success(f"{del_id} ID törölve.")

# --- Main logic 1---
def main():

    if not st.session_state['logged_in']:
        if st.session_state['show_reset']:
            reset_password()
            if st.button("Vissza"):
                st.session_state['show_reset'] = False
        elif st.session_state['show_register']:
            register()
            if st.button("Vissza"):
                st.session_state['show_register'] = False
        else:
            login()
            if st.button("Regisztráció"):
                st.session_state['show_register'] = True
    else:
        if st.button("Kijelentkezés"):
            st.session_state['logged_in'] = False
            st.session_state['username'] = ""
            st.session_state['rerun_flag'] = not st.session_state['rerun_flag']
        else:
            expense_app()

if __name__ == "__main__":
    main()
