module.exports = {
  apps: [{
    name: 'kdt-flask',
    script: 'venv/bin/gunicorn',
    args: '-w 4 -b 0.0.0.0:5000 app:app',
    interpreter: 'none',
    cwd: '/home/ubuntu/kdt_user_login/flask_project'
  }]
}
