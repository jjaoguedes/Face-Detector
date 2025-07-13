document.addEventListener('DOMContentLoaded', async () => {
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  const mensagem = document.getElementById('mensagem');
  const gerarRelatorioSemanal = document.getElementById('gerarRelatorioSemanal');
  const gerarRelatorioMensal = document.getElementById('gerarRelatorioMensal');
  const downloadRelatorio = document.getElementById('downloadRelatorio');

  let membrosPresentes = {}; // Para armazenar os membros que estão presentes e seu tempo de entrada.

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

        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
        enviarParaBackend(blob);
      }
    }, 3000); // Verificação a cada 5000ms
  });

  async function enviarParaBackend(blob) {
    const formData = new FormData();
    formData.append('imagem', blob, 'captura.jpg');

    try {
      const resposta = await fetch('http://localhost:8000/face', {
        method: 'POST',
        body: formData
      });
      const resultado = await resposta.json();

      if (resposta.ok) {
        mensagem.textContent = 'Rosto enviado com sucesso!';

        // Verifica se algum rosto foi detectado
        if (resultado.qtd_rostos_detectados > 0) {
          const nomeMembro = resultado.resultados[0].nome;
          const membroId = resultado.resultados[0].id;

          // Verifica se o membro já está presente
          if (!membrosPresentes[membroId]) {
            // Registra a entrada diretamente no backend
            membrosPresentes[membroId] = Date.now();
            await registrarEntrada(membroId);  // Registra a entrada antes de verificar a saída
          } else {
            // Caso contrário, registra a saída após verificar a entrada
            await registrarSaida(membroId);
          }
        }
      } else {
        mensagem.textContent = 'Erro ao processar rosto: ' + (resultado.erro || 'Erro desconhecido');
      }
    } catch (e) {
      mensagem.textContent = 'Erro ao enviar imagem para o backend.';
      console.error('Erro ao enviar imagem para o backend:', e);
    }
  }

  // Função para registrar a entrada
  async function registrarEntrada(membroId) {
    try {
      const resposta = await fetch(`http://localhost:8000/face`, {
        method: 'POST',
        body: JSON.stringify({ membro_id: membroId }),
        headers: {
          'Content-Type': 'application/json'
        }
      });
      const resultado = await resposta.json();
      if (resposta.ok) {
        mensagem.textContent = `Entrada registrada para o membro ID: ${membroId}`;
      } else {
        mensagem.textContent = 'Erro ao registrar entrada.';
      }
    } catch (e) {
      mensagem.textContent = 'Erro ao registrar entrada.';
      console.error('Erro ao registrar entrada:', e);
    }
  }

  // Função para registrar a saída
  async function registrarSaida(membroId) {
    try {
      const resposta = await fetch(`http://localhost:8000/saida?membro_id=${membroId}`, {
        method: 'POST'
      });
      const resultado = await resposta.json();
      if (resposta.ok) {
        mensagem.textContent = `Saída registrada com sucesso para o membro ID: ${membroId}`;
        // Limpa o membro presente após registrar a saída
        delete membrosPresentes[membroId];
      } else {
        mensagem.textContent = 'Erro ao registrar saída.';
      }
    } catch (e) {
      mensagem.textContent = 'Erro ao registrar saída.';
      console.error('Erro ao registrar saída:', e);
    }
  }

  // Funções para gerar relatórios
  async function gerarRelatorio(tipo) {
    try {
      const resposta = await fetch(`http://localhost:8000/gerar-relatorio/${tipo}`);
      const data = await resposta.blob();
      const url = URL.createObjectURL(data);
      downloadRelatorio.href = url;
      downloadRelatorio.style.display = 'block';
    } catch (e) {
      console.error('Erro ao gerar relatório:', e);
    }
  }

  gerarRelatorioSemanal.addEventListener('click', () => {
    gerarRelatorio('semanal');
  });

  gerarRelatorioMensal.addEventListener('click', () => {
    gerarRelatorio('mensal');
  });

  iniciarCamera();
});
