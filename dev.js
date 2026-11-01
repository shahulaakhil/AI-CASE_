const { spawn, exec } = require('child_process');
const path = require('path');
const os = require('os');

// Detect Local Wi-Fi / Network IP
let networkIp = 'localhost';
const nets = os.networkInterfaces();
for (const name of Object.keys(nets)) {
  for (const net of nets[name]) {
    if (net.family === 'IPv4' && !net.internal && !net.address.startsWith('169.')) {
      networkIp = net.address;
      break;
    }
  }
}

const localUrl = 'http://localhost:8000';
const networkUrl = `http://${networkIp}:8000`;

console.log('\n  \x1b[32m\x1b[1m⚡ AI Case Intelligent is running!\x1b[0m\n');
console.log(`  \x1b[36m\x1b[1m➜  Local:   \x1b[0m\x1b[4m\x1b[36m${localUrl}\x1b[0m`);
console.log(`  \x1b[36m\x1b[1m➜  Network: \x1b[0m\x1b[4m\x1b[36m${networkUrl}\x1b[0m\n`);
console.log('  \x1b[90m➜  Click or Ctrl+Click http://localhost:8000 to open in your browser.\x1b[0m\n');

// Automatically open the website in Chrome/default browser after server initializes
setTimeout(() => {
  exec(`start ${localUrl}`);
}, 1800);

// Resolve python in .venv
const rootDir = path.resolve(__dirname, __dirname.endsWith('LitigatAI') ? '..' : '.');
const litigatDir = path.join(rootDir, 'LitigatAI');
const pythonPath = path.join(rootDir, '.venv', 'Scripts', 'python.exe');

const uvicorn = spawn(
  pythonPath,
  ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000'],
  {
    cwd: litigatDir,
    stdio: 'inherit',
  }
);

uvicorn.on('close', (code) => {
  process.exit(code || 0);
});
