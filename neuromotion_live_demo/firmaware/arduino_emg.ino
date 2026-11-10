const int EMG_PIN = A0;

float filteredEMG = 0;
bool firstReading = true;

unsigned long lastSample = 0;
const unsigned long SAMPLE_INTERVAL = 10000;

void setup() {
  Serial.begin(115200);
}

void loop() {
  unsigned long now = micros();

  if (now - lastSample >= SAMPLE_INTERVAL) {
    lastSample = now;

    int raw = analogRead(EMG_PIN);

    if (firstReading) {
      filteredEMG = raw;
      firstReading = false;
    }

    filteredEMG =
      0.15 * raw +
      0.85 * filteredEMG;

    Serial.print(raw);
    Serial.print(",");
    Serial.println((int)filteredEMG);
  }
}