document.addEventListener('DOMContentLoaded', async () => {
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  const mensagem = document.getElementById('mensagem');

  await Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri('/models')
  ]);

  async function iniciarCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      video.srcObject = stream;
    } catch (erro) {
      mensagem.textContent = 'Erro ao acessar a câmera.';
    }
  }

  video.addEventListener('play', () => {
    const intervalo = setInterval(async () => {
      const detections = await faceapi.detectAllFaces(video, new faceapi.TinyFaceDetectorOptions());
      if (detections.length === 1) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0);
        clearInterval(intervalo);

        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
        enviarParaBackend(blob);
      }
    }, 500);
  });

  async function enviarParaBackend(blob) {
    const formData = new FormData();
    formData.append('imagem', blob, 'captura.jpeg');

    try {
      const resposta = await fetch('http://localhost:8000/face', {
        method: 'POST',
        body: formData
      });
      const resultado = await resposta.json();
      mensagem.textContent = 'Rosto enviado com sucesso: ' + JSON.stringify(resultado);
    } catch (e) {
      mensagem.textContent = 'Erro ao enviar imagem para o backend.';
    }
  }

  iniciarCamera();
});
