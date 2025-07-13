const int ledEntradaPin = 4;  // LED de entrada
const int ledSaidaPin = 2;    // LED de saída

void setup() {
  Serial.begin(9600);
  pinMode(ledEntradaPin, OUTPUT);
  pinMode(ledSaidaPin, OUTPUT);
  digitalWrite(ledEntradaPin, LOW);
  digitalWrite(ledSaidaPin, LOW);
}

void loop() {
  if (Serial.available() > 0) {
    char comando = Serial.read();

    // Ignorar caracteres indesejados
    if (comando == '\n' || comando == '\r' || comando == ' ') {
      return;
    }

    Serial.print("Comando recebido: ");
    Serial.println(comando);

    if (comando == 'e') {
      digitalWrite(ledEntradaPin, HIGH);
      delay(5000);
      digitalWrite(ledEntradaPin, LOW);
    } 
    else if (comando == 's') {
      digitalWrite(ledSaidaPin, HIGH);
      delay(5000);
      digitalWrite(ledSaidaPin, LOW);
    }

    // Limpa o buffer restante (caso venha mais de 1 caractere)
    while (Serial.available() > 0) {
      Serial.read();
    }
  }
}
