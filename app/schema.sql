DROP TABLE IF EXISTS logs;
DROP TABLE IF EXISTS user;

CREATE TABLE logs (
  date TEXT, 
  verb TEXT, 
  setname TEXT, 
  identifier TEXT, 
  datefrom TEXT, 
  dateuntil TEXT
);

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL
);