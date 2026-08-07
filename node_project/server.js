// ─────────────────────────────────────────────
// KDT Resource — Auth Backend (Node.js / Express)
// Stack: Express · Mongoose · bcryptjs · jsonwebtoken
// ─────────────────────────────────────────────
// npm install express mongoose bcryptjs jsonwebtoken dotenv cors

require('dotenv/config');
const express  = require('express');
const mongoose = require('mongoose');
const bcrypt   = require('bcryptjs');
const jwt      = require('jsonwebtoken');
const cors     = require('cors');
const path    = require('path');

const app = express();
app.use(express.json());
app.use(cors());
app.use(express.static(path.join(__dirname, 'public')));

// ── MongoDB connection ──────────────────────
mongoose.connect(process.env.MONGO_URI || 'mongodb://localhost:27017/kdt_resource')
  .then(() => console.log('✅  MongoDB connected'))
  .catch(err => console.error('❌  MongoDB error:', err));

// ── User Schema & Model ─────────────────────
const userSchema = new mongoose.Schema({
  username: { type: String, required: true, unique: true, minlength: 3, trim: true },
  email:    { type: String, required: true, unique: true, lowercase: true, trim: true },
  password: { type: String, required: true },          // bcrypt hash — never stored plain
  createdAt:{ type: Date,   default: Date.now }
});

const User = mongoose.model('User', userSchema);

// ── Helper: sign JWT ────────────────────────
const signToken = (id) =>
  jwt.sign({ id }, process.env.JWT_SECRET || 'changeme_secret', { expiresIn: '7d' });

// ── POST /api/auth/register ─────────────────
app.post('/api/auth/register', async (req, res) => {
  try {
    const { username, email, password } = req.body;

    if (!username || !email || !password)
      return res.status(400).json({ message: 'All fields are required.' });
    if (password.length < 8)
      return res.status(400).json({ message: 'Password must be at least 8 characters.' });

    const exists = await User.findOne({ $or: [{ email }, { username }] });
    if (exists)
      return res.status(409).json({ message: 'Username or email already in use.' });

    const hash = await bcrypt.hash(password, 12);
    const user = await User.create({ username, email, password: hash });

    res.status(201).json({
      message: 'Account created successfully.',
      token:   signToken(user._id),
      user:    { id: user._id, username: user.username, email: user.email }
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error.' });
  }
});

// ── POST /api/auth/login ────────────────────
app.post('/api/auth/login', async (req, res) => {
  try {
    const { email, password } = req.body;

    if (!email || !password)
      return res.status(400).json({ message: 'Email and password are required.' });

    const user = await User.findOne({ email });
    if (!user || !(await bcrypt.compare(password, user.password)))
      return res.status(401).json({ message: 'Invalid email or password.' });

    res.json({
      message: 'Login successful.',
      token:   signToken(user._id),
      user:    { id: user._id, username: user.username, email: user.email }
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ message: 'Server error.' });
  }
});

// ── GET /api/auth/me  (protected example) ──
const authMiddleware = (req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) return res.status(401).json({ message: 'No token provided.' });
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET || 'changeme_secret');
    next();
  } catch {
    res.status(401).json({ message: 'Invalid or expired token.' });
  }
};

app.get('/api/auth/me', authMiddleware, async (req, res) => {
  const user = await User.findById(req.user.id).select('-password');
  res.json(user);
});

// ── Start server ────────────────────────────
const PORT = process.env.PORT || 4000;
app.listen(PORT, () => console.log(`🚀  Server running on http://localhost:${PORT}`));