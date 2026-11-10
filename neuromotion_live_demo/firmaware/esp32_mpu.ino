#include <Wire.h>

const uint8_t MPU = 0x68;

float offsetX = 0;
float offsetY = 0;
float offsetZ = 0;

const float GYRO_SCALE = 131.0;

const float UP_THRESHOLD = 35.0;
const float DOWN_THRESHOLD = -35.0;

const int MPU_DIRECTION = -1;

int repCount = 0;

bool wentUp = false;
bool repActive = false;

unsigned long repStartMs = 0;
unsigned long lastRepMs = 0;
unsigned long lastSampleUs = 0;

float lastRepTimeS = 0.0;

const unsigned long SAMPLE_INTERVAL_US = 20000;
const unsigned long REP_LOCKOUT_MS = 500;

void writeMPU(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool readMPU(
  int16_t &ax,
  int16_t &ay,
  int16_t &az,
  int16_t &gx,
  int16_t &gy,
  int16_t &gz
) {
  Wire.beginTransmission(MPU);
  Wire.write(0x3B);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  if (Wire.requestFrom((int)MPU, 14) != 14) {
    return false;
  }

  ax = (Wire.read() << 8) | Wire.read();
  ay = (Wire.read() << 8) | Wire.read();
  az = (Wire.read() << 8) | Wire.read();

  Wire.read();
  Wire.read();

  gx = (Wire.read() << 8) | Wire.read();
  gy = (Wire.read() << 8) | Wire.read();
  gz = (Wire.read() << 8) | Wire.read();

  return true;
}

void calibrateGyro() {
  long sx = 0;
  long sy = 0;
  long sz = 0;

  int valid = 0;

  for (int i = 0; i < 500; i++) {
    int16_t ax, ay, az;
    int16_t gx, gy, gz;

    if (readMPU(ax, ay, az, gx, gy, gz)) {
      sx += gx;
      sy += gy;
      sz += gz;
      valid++;
    }

    delay(5);
  }

  if (valid > 0) {
    offsetX = sx / (float)valid;
    offsetY = sy / (float)valid;
    offsetZ = sz / (float)valid;
  }
}

void setup() {
  Serial.begin(115200);

  Wire.begin(21, 22);
  Wire.setClock(400000);

  delay(1000);

  Wire.beginTransmission(MPU);

  if (Wire.endTransmission() != 0) {
    while (true) {
      Serial.println("MPU_ERROR");
      delay(1000);
    }
  }

  writeMPU(0x6B, 0x00);
  writeMPU(0x1A, 0x03);
  writeMPU(0x1B, 0x00);
  writeMPU(0x1C, 0x00);

  calibrateGyro();
}

void loop() {
  unsigned long nowUs = micros();

  if (
    nowUs - lastSampleUs <
    SAMPLE_INTERVAL_US
  ) {
    return;
  }

  lastSampleUs = nowUs;

  int16_t ax, ay, az;
  int16_t gxRaw, gyRaw, gzRaw;

  if (!readMPU(
        ax,
        ay,
        az,
        gxRaw,
        gyRaw,
        gzRaw
      )) {
    return;
  }

  float gx =
    (gxRaw - offsetX) /
    GYRO_SCALE;

  float gy =
    (gyRaw - offsetY) /
    GYRO_SCALE;

  float gz =
    (gzRaw - offsetZ) /
    GYRO_SCALE;

  float wrist =
    gy * MPU_DIRECTION;

  String state = "REST";

  if (
    wrist >
    UP_THRESHOLD
  ) {
    state = "WRIST UP";

    if (!repActive) {
      repActive = true;
      repStartMs = millis();
    }

    wentUp = true;
  }

  else if (
    wrist <
    DOWN_THRESHOLD
  ) {
    state = "WRIST DOWN";

    if (
      wentUp &&
      repActive &&
      millis() - lastRepMs >
      REP_LOCKOUT_MS
    ) {
      unsigned long repEndMs =
        millis();

      lastRepTimeS =
        (repEndMs - repStartMs) /
        1000.0;

      repCount++;

      lastRepMs =
        repEndMs;

      wentUp = false;
      repActive = false;
    }
  }

  Serial.print(gx, 1);
  Serial.print(",");

  Serial.print(gy, 1);
  Serial.print(",");

  Serial.print(gz, 1);
  Serial.print(",");

  Serial.print(state);
  Serial.print(",");

  Serial.print(repCount);
  Serial.print(",");

  Serial.println(
    lastRepTimeS,
    3
  );
}