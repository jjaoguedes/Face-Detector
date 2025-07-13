document.addEventListener('DOMContentLoaded', async () => {
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  const mensagem = document.getElementById('mensagem');
  const gerarRelatorioSemanal = document.getElementById('gerarRelatorioSemanal');
  const gerarRelatorioMensal = document.getElementById('gerarRelatorioMensal');
  const downloadRelatorio = document.getElementById('downloadRelatorio');

  let membrosPresentes = {};

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
    }, 3000);
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
        if (resultado.status === 'entrada') {
          mensagem.textContent = `Entrada registrada: ${resultado.nome} (ID ${resultado.membro_id})`;
          membrosPresentes[resultado.membro_id] = Date.now();
        } else if (resultado.status === 'saida') {
          mensagem.textContent = `Saída registrada: ${resultado.nome} (ID ${resultado.membro_id}) - Tempo: ${resultado.tempo_total}s`;
          delete membrosPresentes[resultado.membro_id];
        } else {
          mensagem.textContent = resultado.erro || 'Rosto não reconhecido.';
        }
      } else {
        mensagem.textContent = 'Erro ao processar rosto: ' + (resultado.erro || 'Erro desconhecido');
      }
    } catch (e) {
      mensagem.textContent = 'Erro ao enviar imagem para o backend.';
      console.error('Erro ao enviar imagem para o backend:', e);
    }
  }

  // Geração de relatórios
  async function gerarRelatorio(tipo) {
    try {
      mensagem.textContent = `Gerando relatório ${tipo}...`;
      downloadRelatorio.style.display = 'none';

      const resposta = await fetch(`http://localhost:8000/gerar-relatorio/${tipo}`);
      if (!resposta.ok) {
        throw new Error('Falha ao gerar relatório');
      }

      const blob = await resposta.blob();
      const url = URL.createObjectURL(blob);
      downloadRelatorio.href = url;
      downloadRelatorio.download = `relatorio_${tipo}.xlsx`;
      downloadRelatorio.style.display = 'inline';
      mensagem.textContent = `Relatório ${tipo} pronto para download. Clique no link abaixo.`;
    } catch (e) {
      mensagem.textContent = `Erro ao gerar relatório ${tipo}.`;
      console.error('Erro ao gerar relatório:', e);
    }
  }

  gerarRelatorioSemanal.addEventListener('click', () => gerarRelatorio('semanal'));
  gerarRelatorioMensal.addEventListener('click', () => gerarRelatorio('mensal'));

  iniciarCamera();
});
