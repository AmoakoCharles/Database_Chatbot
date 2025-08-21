import tkinter as tk
import os
from tkinter import messagebox, ttk
import hashlib
from together import Together
from dotenv import load_dotenv
import mysql.connector


load_dotenv()
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")

# Initialize Together API
client = Together(api_key=TOGETHER_API_KEY)


# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    
# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Discover schema and foreign key relationships
def discover_schema():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE();")
    columns_data = cursor.fetchall()

    schema = {}
    for table, column in columns_data:
        schema.setdefault(table, []).append(column)

    cursor.execute("""
        SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE REFERENCED_TABLE_NAME IS NOT NULL AND TABLE_SCHEMA = DATABASE();
    """)
    fk_data = cursor.fetchall()

    relationships = []
    for table, column, ref_table, ref_column in fk_data:
        relationships.append(f"{table}.{column} → {ref_table}.{ref_column}")

    prompt_lines = []
    for table, columns in schema.items():
        prompt_lines.append(f"Table: {table}")
        prompt_lines.append(f"Columns: {', '.join(columns)}")
        prompt_lines.append("")

    if relationships:
        prompt_lines.append("Foreign Key Relationships:")
        for rel in relationships:
            prompt_lines.append(f"- {rel}")
        prompt_lines.append("")

    prompt_lines.append("Use JOINs based on foreign key relationships when needed to answer the query.")
    prompt_lines.append("Avoid ambiguous aliases unless clearly defined. Prefer full table names for clarity.")

    cursor.close()
    conn.close()
    return "\n".join(prompt_lines)

# Generate SQL from natural language
def generate_sql(nl_query, schema_info):
    prompt = f"""
You are a helpful assistant that converts natural language questions into SQL SELECT queries.
Use the following database schema to guide your query generation.

{schema_info}

Question: {nl_query}
SQL:
"""
    response = client.chat.completions.create(
        model="mistralai/Mistral-7B-Instruct-v0.2",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    sql = response.choices[0].message.content.strip()
    if not sql.lower().startswith("select"):
        raise ValueError("The AI did not return a valid SELECT query.")
    return sql

# Execute SQL and return results
def execute_sql(sql):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return columns, rows

# GUI: Login Window
class LoginWindow:
    def __init__(self, master):
        self.master = master
        master.title("Login")

        tk.Label(master, text="Username").grid(row=0)
        tk.Label(master, text="Password").grid(row=1)

        self.username_entry = tk.Entry(master)
        self.password_entry = tk.Entry(master, show="*")

        self.username_entry.grid(row=0, column=1)
        self.password_entry.grid(row=1, column=1)

        tk.Button(master, text="Login", command=self.login).grid(row=2, column=0)
        tk.Button(master, text="Sign Up", command=self.open_signup).grid(row=2, column=1)

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        hashed = hash_password(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, hashed))
        result = cursor.fetchone()
        cursor.close()
        conn.close()

        if result:
            self.master.destroy()
            root = tk.Tk()
            MainApp(root)
            root.mainloop()
        else:
            messagebox.showerror("Error", "Invalid credentials")

    def open_signup(self):
        self.master.destroy()
        root = tk.Tk()
        SignupWindow(root)
        root.mainloop()

# GUI: Signup Window
class SignupWindow:
    def __init__(self, master):
        self.master = master
        master.title("Sign Up")

        tk.Label(master, text="Username").grid(row=0)
        tk.Label(master, text="Password").grid(row=1)

        self.username_entry = tk.Entry(master)
        self.password_entry = tk.Entry(master, show="*")

        self.username_entry.grid(row=0, column=1)
        self.password_entry.grid(row=1, column=1)

        tk.Button(master, text="Sign Up", command=self.signup).grid(row=2, column=0)
        tk.Button(master, text="Back to Login", command=self.back_to_login).grid(row=2, column=1)

    def signup(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        hashed = hash_password(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed))
        conn.commit()
        cursor.close()
        conn.close()

        messagebox.showinfo("Success", "Account created!")
        self.back_to_login()

    def back_to_login(self):
        self.master.destroy()
        root = tk.Tk()
        LoginWindow(root)
        root.mainloop()

# GUI: Main Application
class MainApp:
    def __init__(self, master):
        self.master = master
        master.title("Natural Language to SQL")

        tk.Label(master, text="Enter your question:").pack()
        self.query_entry = tk.Entry(master, width=80)
        self.query_entry.pack()

        tk.Button(master, text="Submit", command=self.process_query).pack()

        self.tree = ttk.Treeview(master)
        self.tree.pack(fill=tk.BOTH, expand=True)

    def process_query(self):
        nl_query = self.query_entry.get()
        try:
            schema_info = discover_schema()
            sql = generate_sql(nl_query, schema_info)
            columns, rows = execute_sql(sql)

            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = columns
            self.tree["show"] = "headings"
            for col in columns:
                self.tree.heading(col, text=col)
                self.tree.column(col, width=100)

            for row in rows:
                self.tree.insert("", "end", values=row)

        except Exception as e:
            messagebox.showerror("Error", str(e))

# Start the application
if __name__ == "__main__":
    root = tk.Tk()
    LoginWindow(root)
    root.mainloop()
