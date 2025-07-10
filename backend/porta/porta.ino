// Definir os pinos dos LEDs
const int ledEntradaPin = 13;  // LED de entrada no pino 13
const int ledSaidaPin = 12;    // LED de saída no pino 12

void setup() {
  // Iniciar comunicação serial
  Serial.begin(9600);

  // Configurar os pinos dos LEDs como saída
  pinMode(ledEntradaPin, OUTPUT);
  pinMode(ledSaidaPin, OUTPUT);

  // Inicializar LEDs apagados
  digitalWrite(ledEntradaPin, LOW);
  digitalWrite(ledSaidaPin, LOW);
}

void loop() {
  // Verificar se há dados recebidos pela serial
  if (Serial.available() > 0) {
    // Ler o comando enviado pelo backend
    char comando = Serial.read();

    // Se o comando for 'entrada', aciona o LED de entrada
    if (comando == 'entrada') {
      digitalWrite(ledEntradaPin, HIGH);  // Aciona LED de entrada
      delay(5000);  // Mantém o LED aceso por 5 segundos
      digitalWrite(ledEntradaPin, LOW);   // Desliga o LED de entrada após 5 segundos
    }

    // Se o comando for 'saida', aciona o LED de saída
    else if (comando == 'saida') {
      digitalWrite(ledSaidaPin, HIGH);    // Aciona LED de saída
      delay(5000);  // Mantém o LED aceso por 5 segundos
      digitalWrite(ledSaidaPin, LOW);     // Desliga o LED de saída após 5 segundos
    }
  }
}
