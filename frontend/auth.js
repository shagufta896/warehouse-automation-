const API = '';
let currentMode = 'login'; // login, signup, otp
let otpPurpose = '';
let currentEmail = '';

function toast(msg, type = 'info') {
  const c = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  el.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${msg}</span>`;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

function toggleMode(mode) {
  document.getElementById('loginCard').classList.add('hidden');
  document.getElementById('signupCard').classList.add('hidden');
  document.getElementById('otpCard').classList.add('hidden');
  
  if (mode === 'login') document.getElementById('loginCard').classList.remove('hidden');
  if (mode === 'signup') document.getElementById('signupCard').classList.remove('hidden');
  if (mode === 'otp') document.getElementById('otpCard').classList.remove('hidden');
}

async function login() {
  const email = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;
  
  if (!email || !password) {
    return toast('Please enter email and password', 'error');
  }

  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Login failed');

    currentEmail = email;
    otpPurpose = 'login';
    toast('OTP sent to your email', 'success');
    toggleMode('otp');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function sendSignupOTP() {
  const email = document.getElementById('signupEmail').value.trim();
  const password = document.getElementById('signupPassword').value;
  const name = document.getElementById('signupName').value.trim();

  if (!email || !password || !name) {
    return toast('Please fill all required fields', 'error');
  }

  try {
    const res = await fetch(`${API}/auth/send-otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, purpose: 'signup' })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to send OTP');

    currentEmail = email;
    otpPurpose = 'signup';
    toast('OTP sent to your email', 'success');
    toggleMode('otp');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function verifyOTP() {
  const otp = document.getElementById('otpCode').value.trim();
  if (!otp) return toast('Please enter OTP', 'error');

  try {
    let res, data;
    if (otpPurpose === 'login') {
      res = await fetch(`${API}/auth/verify-login-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: currentEmail, otp, purpose: 'login' })
      });
      data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Invalid OTP');
    } else if (otpPurpose === 'signup') {
      const name = document.getElementById('signupName').value.trim();
      const store = document.getElementById('signupStore').value.trim();
      const password = document.getElementById('signupPassword').value;

      res = await fetch(`${API}/auth/signup?otp=${otp}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: name, store_name: store, email: currentEmail, password })
      });
      data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Signup failed');
    }

    // Success - Save token and redirect
    localStorage.setItem('access_token', data.access_token);
    window.location.href = 'index.html';

  } catch (err) {
    toast(err.message, 'error');
  }
}

// Redirect if already logged in
if (localStorage.getItem('access_token')) {
  window.location.href = 'index.html';
}
