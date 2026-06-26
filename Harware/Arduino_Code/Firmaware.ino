#include <Wire.h>
#include <math.h>

#define MPU 0x68

#define LED_PIN 7
#define BUZZER_PIN 8

float maxTilt = 0;
int alertCount = 0;

bool dangerState = false;

void setup()
{
    Serial.begin(9600);

    Wire.begin();

    pinMode(LED_PIN,OUTPUT);
    pinMode(BUZZER_PIN,OUTPUT);

    Wire.beginTransmission(MPU);
    Wire.write(0x6B);
    Wire.write(0);
    Wire.endTransmission();

    Wire.beginTransmission(MPU);
    Wire.write(0x1C);
    Wire.write(0x00);
    Wire.endTransmission();
}

void loop()
{
    int16_t ax,ay,az,temp;

    Wire.beginTransmission(MPU);
    Wire.write(0x3B);
    Wire.endTransmission(false);

    Wire.requestFrom(MPU,8,true);

    ax=(Wire.read()<<8)|Wire.read();
    ay=(Wire.read()<<8)|Wire.read();
    az=(Wire.read()<<8)|Wire.read();

    temp=(Wire.read()<<8)|Wire.read();

    float AccX=ax/16384.0;
    float AccY=ay/16384.0;
    float AccZ=az/16384.0;

    float temperature=(temp/340.0)+36.53;

    float roll=atan2(AccY,AccZ)*180.0/PI;

    float pitch=atan2(-AccX,
                      sqrt(AccY*AccY+AccZ*AccZ))
                      *180.0/PI;

    float tilt=max(abs(roll),abs(pitch));

    if(tilt>maxTilt)
        maxTilt=tilt;

    String status;

    if(tilt<10)
    {
        status="SAFE";

        digitalWrite(LED_PIN,LOW);
        digitalWrite(BUZZER_PIN,LOW);

        dangerState=false;
    }
    else if(tilt<20)
    {
        status="WARNING";

        digitalWrite(LED_PIN,HIGH);
        digitalWrite(BUZZER_PIN,LOW);

        dangerState=false;
    }
    else
    {
        status="DANGER";

        digitalWrite(LED_PIN,HIGH);

        tone(BUZZER_PIN,2000);

        if(!dangerState)
        {
            alertCount++;
            dangerState=true;
        }
    }

    if(status!="DANGER")
    {
        noTone(BUZZER_PIN);
    }

    Serial.print(roll,2);
    Serial.print(",");

    Serial.print(pitch,2);
    Serial.print(",");

    Serial.print(temperature,2);
    Serial.print(",");

    Serial.print(maxTilt,2);
    Serial.print(",");

    Serial.print(status);
    Serial.print(",");

    Serial.println(alertCount);

    delay(100);
}