const express = require('express');
const app = express();
const mysql = require('mysql');

// Hard-coded credentials
const API_KEY = 'sk-1234567890abcdef';
const DB_PASSWORD = 'admin123';

// SQL Injection vulnerability
app.get('/user', (req, res) => {
    const userId = req.query.id;
    const query = `SELECT * FROM users WHERE id = ${userId}`; // SQL injection
    res.send(query);
});

// Command injection
app.get('/ping', (req, res) => {
    const host = req.query.host;
    const { exec } = require('child_process');
    exec(`ping ${host}`, (error, stdout, stderr) => { // Command injection
        res.send(stdout);
    });
});

// XSS vulnerability
app.get('/search', (req, res) => {
    const query = req.query.q;
    res.send(`<h1>Search results for: ${query}</h1>`); // XSS
});

app.listen(3000);