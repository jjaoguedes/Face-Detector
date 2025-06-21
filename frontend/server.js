const express = require('express');
const app = express();
const path = require('path');

app.use(express.static(path.join(__dirname, 'src')));
app.use(express.static(path.join(__dirname, 'public')));

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'src/index.html'));
});

const PORT = 3000;
app.listen(PORT, () => {
  console.log(`Frontend rodando em http://localhost:${PORT}`);
});
