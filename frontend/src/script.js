document.addEventListener('DOMContentLoaded', async () => {
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  const mensagem = document.getElementById('mensagem');
  const gerarRelatorioSemanal = document.getElementById('gerarRelatorioSemanal');
  const gerarRelatorioMensal = document.getElementById('gerarRelatorioMensal');
  const downloadRelatorio = document.getElementById('downloadRelatorio');

  let membrosPresentes = {};
  let bloqueadoTemporariamente = false;

  await Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri('/models')
  ]);

  async function iniciarCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      video.srcObject = stream;
    } catch (erro) {
      mensagem.textContent = '❌ Erro ao acessar a câmera.';
    }
  }

  video.addEventListener('play', () => {
    setInterval(async () => {
      if (bloqueadoTemporariamente) return;

      const detections = await faceapi.detectAllFaces(video, new faceapi.TinyFaceDetectorOptions());

      if (detections.length === 1) {
        const box = detections[0].box;
        const tamanhoMinimo = 80;

        if (box.width < tamanhoMinimo || box.height < tamanhoMinimo) {
          mensagem.textContent = '📏 Aproxime o rosto da câmera.';
          return;
        }

        mensagem.textContent = '🔍 Rosto detectado. Verificando...';

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d').drawImage(video, 0, 0);

        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
        await enviarParaBackend(blob);
      } else if (detections.length > 1) {
        mensagem.textContent = '👥 Vários rostos detectados. Posicione apenas um.';
      } else {
        mensagem.textContent = '🕵️‍♂️ Aguardando rosto...';
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
          mensagem.textContent = `✅ Entrada: ${resultado.nome} (ID ${resultado.membro_id})`;
          membrosPresentes[resultado.membro_id] = Date.now();
        } else if (resultado.status === 'saida') {
          mensagem.textContent = `👋 Saída: ${resultado.nome} (ID ${resultado.membro_id}) - Tempo: ${resultado.tempo_total}s`;
          delete membrosPresentes[resultado.membro_id];
        } else if (resultado.erro) {
          mensagem.textContent = `⚠️ ${resultado.erro}`;
          if (resultado.erro.includes('Muitas tentativas')) {
            bloquearTemporariamente();
          }
        }
      } else {
        mensagem.textContent = '❌ Erro ao processar rosto.';
      }
    } catch (e) {
      mensagem.textContent = '🚫 Erro na conexão com o backend.';
      console.error('Erro ao enviar imagem para o backend:', e);
    }
  }

  function bloquearTemporariamente() {
    bloqueadoTemporariamente = true;
    mensagem.textContent = '🔒 Acesso bloqueado temporariamente. Aguarde 5 minutos.';
    gerarRelatorioMensal.disabled = true;
    gerarRelatorioSemanal.disabled = true;

    setTimeout(() => {
      bloqueadoTemporariamente = false;
      mensagem.textContent = '🔓 Você pode tentar novamente.';
      gerarRelatorioMensal.disabled = false;
      gerarRelatorioSemanal.disabled = false;
    }, 5 * 60 * 1000); // 5 minutos
  }

  async function gerarRelatorio(tipo) {
    try {
      mensagem.textContent = `📄 Gerando relatório ${tipo}...`;
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
      mensagem.textContent = `📥 Relatório ${tipo} pronto para download.`;
    } catch (e) {
      mensagem.textContent = `❌ Erro ao gerar relatório ${tipo}.`;
      console.error('Erro ao gerar relatório:', e);
    }
  }

  gerarRelatorioSemanal.addEventListener('click', () => gerarRelatorio('semanal'));
  gerarRelatorioMensal.addEventListener('click', () => gerarRelatorio('mensal'));

  iniciarCamera();
});
