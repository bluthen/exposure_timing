//date:    2024-01-08
//author:  Krzysztof Kamiński
//email:   chrisk@amu.edu.pl
//licence: CC BY-SA 4.0
//************************************
//NEXTA - New EXposure Timing Analyser
//************************************
//hardware:
//Arduino Due
//+ Proto Shield
//+ GPS NEO 7: RX1, TX1, 0.1Hz PPS -> D3 pin, 3.3V
//+ KingBright 20 LED stripe: digital pins from 22 to 41
//software:
//Arduino IDE 1.8.19
//Arduino SAM Boards 1.6.12

#define correct_drift           //if correct_drift is defined (uncommented) than Arduino clock drift correction will be implemented at the expense of slightly longer loop time
#define GPS_wait_for_fix 1      //should NEXTA wait for fix after power up? (0-no, 1-yes)
#define GPS_wait_for_drift 1    //should NEXTA callibrate itself after power up? (0-no, 1-yes)
#define Arduino_drift_limit 10  //maximum acceptable Arduino clock drift in microsec / sec, default 10
#define GPS_pps 3               //external interrupt pin number

//calculate checksum of UBX message that is sent to GPS
void calcChecksum(byte *checksumPayload, byte payloadSize)
{
    byte CK_A = 0, CK_B = 0;
    for (int i = 0; i < payloadSize ;i++)
    {
        CK_A = CK_A + *checksumPayload;
        CK_B = CK_B + CK_A;
        checksumPayload++;
    }
    *checksumPayload = CK_A;
    checksumPayload++;
    *checksumPayload = CK_B;
}

//send message to GPS and wait for acknowledgement
//return 0 if message was sent and proper acknowledgment was received
byte getUBX_ACK(byte *msgID)
{
    byte CK_A = 0, CK_B = 0;
    byte incoming_char;
    boolean headerReceived = false;
    unsigned long ackWait = millis();
    byte ackPacket[10] = {0xB5, 0x62, 0x05, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
    int i = 0;
    //Serial.print(" waiting for ack...");
    while (1)
    {
        if (Serial1.available())
        {
            incoming_char = Serial1.read();
            if (incoming_char == ackPacket[i])
            {
                i++;
            }
            else if (i > 2)
            {
                ackPacket[i] = incoming_char;
                i++;
            }
        }
        if (i > 9) break;
        if ((millis() - ackWait) > 1500)
        {
            Serial.println("timeout");
            Serial.println(i);
            return 5;
        }
        if (i == 4 && ackPacket[3] == 0x00)
        {
            Serial.println("not-ack received");
            return 1;
        }
    }

    for (i = 2; i < 8 ;i++)
    {
        CK_A = CK_A + ackPacket[i];
        CK_B = CK_B + CK_A;
    }
    if (msgID[0] == ackPacket[6] && msgID[1] == ackPacket[7] && CK_A == ackPacket[8] && CK_B == ackPacket[9])
    {
        //Serial.println("ack received");
        return 0;
    }
    else
    {
        Serial.print("ack checksum failure ");
        //printlnHex(ackPacket, sizeof(ackPacket));
        delay(100);
        return 1;
    }
}

//get text form GPS - response from previously sent command
int getUBX(byte resp[], int& len)
{
    byte incoming_char;
    unsigned long ackWait = millis();
    byte start[5] = {0x00, 0x00, 0x00, 0x00, 0x00};
    int i = -1;

    //Serial.print(" waiting for response...");
    while (1)
    {
        if (Serial1.available())
        {
            incoming_char = Serial1.read();
            //Serial.print((char)incoming_char);
            if(i>=len || i>=100)
            {
                break;
            }
            if (incoming_char == 181) //0xB5
            {
                i=0;
            }
            if(i>4)
            {
                resp[i]=incoming_char;
                i++;
            }
            if(i==4)
            {
                len = incoming_char+6;

                resp[0]=start[0];
                resp[1]=start[1];
                resp[2]=start[2];
                resp[3]=start[3];
                resp[4]=incoming_char;
                i++;
            }
            if(i>=0 && i<4)
            {
                start[i] = incoming_char;
                i++;
            }
        }
        if ((millis() - ackWait) > 20)
        {
            //Serial.println("timeout.");
            //Serial.println(i);
            //Serial.print("  Response: len=");
            //Serial.print(len);
            //Serial.print(", ");
            //printlnHex(resp, len);
            return 1;
        }
    }

    //Serial.println("response received.");
    //Serial.print("  Response: len=");
    //Serial.println(len);
    //Serial.print(", ");
    //printlnHex(resp, len);
    return 0;
}

//set GPS for time functions
void setSerial()
{
    Serial.print("GPS - setting serial speed to 57600    ");
    byte message[] = {0xB5, 0x62, 0x06, 0x00,
      0x14, 0x00, //message length = 20 bytes
      0x01, 0x00, //port ID, reserved
      0x00, 0x00, //txReady disabled
      0xD0, 0x08, 0x00, 0x00, //UART mode (NEO 7 old UBX protocol version)
//      0xC0, 0x08, 0x00, 0x00, //UART mode
      0x00, 0xE1, 0x00, 0x00, //baud rate
      0x07, 0x00, //inMask (UBOX, NMEA and RTCM2 protocols enabled)
      0x03, 0x00, //outMask (UBOX, NMEA protocols enabled)
      0x00, 0x00, //bit flags (extended TX timeout disabled)
      0x00, 0x00, //reserved, reserved
      0x00, 0x00}; //empty bytes for checksum
    calcChecksum(&message[2], sizeof(message) - 4); //calculate checksum
    Serial1.write(message, sizeof(message));
    Serial1.flush();

    //getUBX_ACK(&message[2], 1); -> this does not work
    Serial.println("ok");
}

//get software and hardware version
void getVersion()
{
    Serial.print("GPS - get software version   ");
    byte message[] = {0xB5, 0x62, 0x0A, 0x04,
      0x00, 0x00, //message length = 0 bytes
      0x00, 0x00}; //empty bytes for checksum
    calcChecksum(&message[2], sizeof(message) - 4); //calculate checksum
    Serial1.write(message, sizeof(message));
    Serial1.flush();
    delay(3050);

    int len=100;
    byte resp[len];
    if( getUBX(resp, len)==0 )
    {
        Serial.println("ok");
    }
    else
    {
        Serial.println("unknown");
    }
}

//set GPS for time functions
void setRate()
{
    Serial.print("GPS - setting measurement rate 0.1Hz   ");
    byte message[] = {0xB5, 0x62, 0x06, 0x08, //command: CFG-RATE
      0x06, 0x00,  //message length = 6 bytes
      0xE8, 0x03,  //measurement rate 10000 ms  (0x64, 0x00,  //measurement rate 100 ms)
      0x01, 0x00,  //fixed = 0x01, 0x00
      0x00, 0x00,  //reference time: UTC = 0x00. 0x00 ; GPS = 0x01, 0x00   (NEO 7 old UBX protocol version)
//      0x00, 0x00,  //reference time: UTC = 0x00. 0x00 ; GPS = 0x01, 0x00
      0x00, 0x00}; //empty bytes for checksum    
    calcChecksum(&message[2], sizeof(message) - 4); //calculate checksum
    Serial1.write(message, sizeof(message));
    Serial1.flush();
    if( getUBX_ACK(&message[2])==0 )
    {
        Serial.println("ok");
    }
    else
    {
        Serial.println("error");
    }
}

//set GPS for time functions
void setSBAS()
{
    Serial.print("GPS - disable SBAS   ");
    //byte setSBAS[] = {0xB5, 0x62, 0x06, 0x16, 0x08, 0x00, 0x01, 0x03, 0x03, 0x00, 0xD1, 0xA2, 0x06, 0x00, 0x00, 0x00};
    byte setSBAS[] = {0xB5, 0x62, 0x06, 0x16, 0x08, 0x00, 0x00, 0x00, 0x03, 0x00, 0xD1, 0xA2, 0x06, 0x00, 0x00, 0x00};
    calcChecksum(&setSBAS[2], sizeof(setSBAS) - 4); //calculate checksum
    Serial1.write(setSBAS, sizeof(setSBAS));
    Serial1.flush();
    getUBX_ACK(&setSBAS[2]);
  
    //Serial.println("Current SBAS settings");
    byte getSBAS[] = {0xB5, 0x62, 0x06, 0x16, 0x00, 0x00, 0x00, 0x00};
    calcChecksum(&getSBAS[2], sizeof(getSBAS) - 4); //calculate checksum
    Serial1.write(getSBAS, sizeof(getSBAS));
    Serial1.flush();

    int len=50;
    byte resp[len];
    if( getUBX(resp, len)==0 )
    {
        if(resp[6]==0) Serial.println("ok");
        else Serial.println("error");
    }

    getUBX_ACK(&getSBAS[2]);

}

//set GPS for time functions
void setMessage()
{
    Serial.print("GPS - turn off GLL   ");
    byte setGLL[] = {0xB5, 0x62, 0x06, 0x01, 0x08, 0x00, 0xF0, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x2B};
    Serial1.write(setGLL, sizeof(setGLL));
    Serial1.flush();
    if( getUBX_ACK(&setGLL[2]) == 0 ) Serial.println("ok");
    else  Serial.println("error");

    Serial.print("GPS - turn off GSA   ");
    byte setGSA[] = {0xB5, 0x62, 0x06, 0x01, 0x08, 0x00, 0xF0, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x32};
    Serial1.write(setGSA, sizeof(setGSA));
    Serial1.flush();
    if( getUBX_ACK(&setGSA[2]) == 0 ) Serial.println("ok");
    else  Serial.println("error");

    Serial.print("GPS - turn off GSV   ");
    byte setGSV[] = {0xB5, 0x62, 0x06, 0x01, 0x08, 0x00, 0xF0, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x03, 0x39};
    Serial1.write(setGSV, sizeof(setGSV));
    Serial1.flush();
    if( getUBX_ACK(&setGSV[2]) == 0 ) Serial.println("ok");
    else  Serial.println("error");

    Serial.print("GPS - turn off RMC   ");
    byte setRMC[] = {0xB5, 0x62, 0x06, 0x01, 0x08, 0x00, 0xF0, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x04, 0x40};
    Serial1.write(setRMC, sizeof(setRMC));
    Serial1.flush();
    if( getUBX_ACK(&setRMC[2]) == 0 ) Serial.println("ok");
    else  Serial.println("error");

    Serial.print("GPS - turn off VTG   ");
    byte setVTG[] = {0xB5, 0x62, 0x06, 0x01, 0x08, 0x00, 0xF0, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x46};
    Serial1.write(setVTG, sizeof(setVTG));
    Serial1.flush();
    if( getUBX_ACK(&setVTG[2]) == 0 ) Serial.println("ok");
    else  Serial.println("error");

    Serial.print("GPS - turn off GGA   ");
    byte setGGA[] = {0xB5, 0x62, 0x06, 0x01, 0x08, 0x00, 0xF0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x23};
    Serial1.write(setGGA, sizeof(setGGA));
    Serial1.flush();
    if( getUBX_ACK(&setGGA[2]) == 0 ) Serial.println("ok");
    else  Serial.println("error");
}

//set GPS for time functions
void setTime(byte serialprint)
{
    Serial.print("GPS - disable TIMEPULSE2   ");
    //                                                      TP2,    0,    0,    0, ant. delay,   FR delay,              period us,       period locked us,        pulse length us, pulse length locked us,     user time delay ns, flags (UTC time base)
    byte setTP5_2[] = {0xB5, 0x62, 0x06, 0x31, 0x20, 0x00, 0x01, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x40, 0x42, 0x0F, 0x00, 0x40, 0x42, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0xA0, 0x86, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x76, 0x00, 0x00, 0x00, 0x00, 0x00};
    calcChecksum(&setTP5_2[2], sizeof(setTP5_2) - 4); //calculate checksum
    Serial1.write(setTP5_2, sizeof(setTP5_2));
    Serial1.flush();
    if( getUBX_ACK(&setTP5_2[2]) == 0 ) Serial.println("ok");
    else Serial.println("error");
    
    Serial.print("GPS - setup TIMEPULSE   ");
    ////                                                      0,    0,    0,    0, ant. delay,   FR delay,              period us,       period locked us,        pulse length us, pulse length locked us,     user time delay ns, flags (GPS time base)
    //byte setTP5[] = {0xB5, 0x62, 0x06, 0x31, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x40, 0x42, 0x0F, 0x00, 0x40, 0x42, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0xA0, 0x86, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF7, 0x00, 0x00, 0x00, 0x00, 0x00};
    //                                                      0,    0,    0,    0, ant. delay,   FR delay,              period us,       period locked us,        pulse length us, pulse length locked us,     user time delay ns, flags (UTC time base)
    //byte setTP5[] = {0xB5, 0x62, 0x06, 0x31, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x40, 0x42, 0x0F, 0x00, 0x40, 0x42, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0xA0, 0x86, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x77, 0x00, 0x00, 0x00, 0x00, 0x00};
    //                                                      0,    0,    0,    0, ant. delay,   FR delay,              period us,       period locked us,        pulse length us, pulse length locked us,     user time delay ns, flags (UTC time base)
    byte setTP5[] = {0xB5, 0x62, 0x06, 0x31, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x32, 0x00, 0x00, 0x00, 0x80, 0x96, 0x98, 0x00, 0x80, 0x96, 0x98, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x42, 0x0F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x77, 0x00, 0x00, 0x00, 0x00, 0x00};
    calcChecksum(&setTP5[2], sizeof(setTP5) - 4); //calculate checksum
    Serial1.write(setTP5, sizeof(setTP5));
    Serial1.flush();
    if( getUBX_ACK(&setTP5[2]) == 0 ) Serial.println("ok");
    else Serial.println("error");

    delay(1500);

        Serial.println("GPS - current timepulse settings");
        byte getTP5[] = {0xB5, 0x62, 0x06, 0x31, 0x00, 0x00, 0x00, 0x00};
        calcChecksum(&getTP5[2], sizeof(getTP5) - 4); //calculate checksum
        Serial1.write(getTP5, sizeof(getTP5));
        Serial1.flush();
        
        int len=50;
        byte resp[len];
        if(getUBX(resp, len)==0)
        {        
            if(resp[6]==0) Serial.println(" Type: TIMEPULSE");
            if(resp[6]==1) Serial.println(" Type: TIMEPULSE2");
        
            Serial.print(" Antenna cable delay: ");
            Serial.print(resp[10]+256L*resp[11]);
            Serial.println(" ns");
        
            Serial.print(" RF group delay: ");
            Serial.print(resp[12]+256L*resp[13]);
            Serial.println(" ns");
        
            Serial.print(" User config delay: ");
            Serial.print(resp[30]+256L*resp[31]+256L*256L*resp[32]+256L*256L*256L*resp[33]);
            Serial.println(" us");
        
            Serial.print(" Period (or freq): ");
            Serial.print(resp[14]+256L*resp[15]+256L*256L*resp[16]+256L*256L*256L*resp[17]);
            Serial.println(" us (or Hz)");
        
            Serial.print(" Period (or freq) - GPS locked: ");
            Serial.print(resp[18]+256L*resp[19]+256L*256L*resp[20]+256L*256L*256L*resp[21]);
            Serial.println(" us (or Hz)");
        
            Serial.print(" Puls length (or duty cycle): ");
            Serial.print(resp[22]+256L*resp[23]+256L*256L*resp[24]+256L*256L*256L*resp[25]);
            Serial.println(" us (or 2^-32)");
        
            Serial.print(" Puls length (or duty cycle) - GPS locked: ");
            Serial.print(resp[26]+256L*resp[27]+256L*256L*resp[28]+256L*256L*256L*resp[29]);
            Serial.println(" us (or 2^-32)");
        
            Serial.print(" Flags (0-UTC 1-GPS, 0-falling 1-rising, alignToTop, isLength, isFreq, lockOther, lockGPS, active): ");
            Serial.println(resp[34], BIN);
    
        }
    
        getUBX_ACK(&setTP5[2]);
}





//test UTC tima validity (if leap seconds are correctly taken into account)
//return: -2 if unknown
//        -1 if leap seconds are not valid
//        >=0 - current number of leap seconds
int getUTCvalid(byte serialprint)
{
        if(serialprint==1) Serial.print("GPS - leap seconds: ");  
        byte getUTCvalid[] = {0xB5, 0x62, 0x01, 0x20, 0x00, 0x00, 0x00, 0x00};
        calcChecksum(&getUTCvalid[2], sizeof(getUTCvalid) - 4); //calculate checksum
        Serial1.write(getUTCvalid, sizeof(getUTCvalid));
        Serial1.flush();

        int len=50;
        byte resp[len];
        if(getUBX(resp, len)==0)
        {
            if(serialprint==1)
            {
                //Serial.print(" Flags (...): ");
                //Serial.print(resp[6+11]);
                //Serial.print(" ");
                //Serial.println(resp[6+11], BIN);
                //Serial.print(" ");
                //Serial.print(resp[6+10]);
                //Serial.print(" ");
                //Serial.print(resp[18]+256L*resp[19]+256L*256L*resp[20]+256L*256L*256L*resp[21]);
                //Serial.print(" ");
            }

            if ( resp[6+11] == 0b00000111 )
            {
                if(serialprint==1)
                {
                    Serial.print("  valid, ");
                    Serial.print(resp[6+10]);
                    Serial.println(" sec");
                }
                return resp[6+10];
            }
            else
            {
                if(serialprint==1) Serial.println("  not valid");
                return -1;
            }
        }
        else
        {
          if(serialprint==1) Serial.println(" Error");
          return -2;
        }
}






//get GPS time message, convert it to JD and later to date and time in GPS_ref_text
int getTM(byte printserial)
{  
    byte getTM[] = {0xB5, 0x62, 0x0D, 0x01, 0x00, 0x00, 0x00, 0x00};
    calcChecksum(&getTM[2], sizeof(getTM) - 4); //calculate checksum

    int len=50;
    byte resp[len];
    long nr_of_weeks, tow, tow_day, tow_h, tow_m, tow_s, rest;
    char text[50];

    while(1)
    {
        Serial1.write(getTM, sizeof(getTM));
        Serial1.flush();
        if( getUBX(resp, len) == 0 && len==22) continue;
        else
        {
            len=22;
            break;
        }
    }

    if( len==22 )
    {
        tow = resp[6]+256L*resp[7]+256L*256L*resp[8]+256L*256L*256L*resp[9];

        tow_day = tow / 86400000;
        rest = tow % 86400000;
        tow_h = ( rest ) / 3600000;
        rest = rest % 3600000;
        tow_m = ( rest ) / 60000;
        rest = rest % 60000;
        tow_s = ( rest ) / 1000;

        nr_of_weeks = resp[18]+256L*resp[19];
    }
    else return 1;

    if( len==22 && resp[0] == 181 && resp[1] == 98 && resp[2] == 13 && resp[3] == 1 && resp[20] == 3 )       //NEO 7 old UBX protocol version
    //if( len==22 && resp[0] == 181 && resp[1] == 98 && resp[2] == 13 && resp[3] == 1 && resp[20] == 11 )        //NEO 8
    {
        if(printserial==1)
        {
            Serial.print("  GPS day of week: ");
            Serial.print(tow_day);
            Serial.print(" time: ");
            Serial.print(tow_h);
            Serial.print(":");
            Serial.print(tow_m);
            Serial.print(":");
            Serial.println(tow_s);
        }

        return 0;
    }
    else
    {
        //Serial.println("get TM error");
        return 1;
    }

    return 1;
}

bool stop_work=0;
byte i, m1;
unsigned long GPS_ref_micros=0;
volatile unsigned long us, last_us, last_accepted_us;
unsigned long delta_us, old_delta_us, old_us;
long median_drift=-9;

void setup()
{
  pinMode(12, OUTPUT);

    //setup digital pins (all, although we use only 22-41 for LEDS, and 3 other for GPS)
    for(i=22; i<42; i++) digitalWrite(i, LOW);
    for(i=22; i<42; i++) pinMode(i, OUTPUT);
    for(i=22; i<42; i++) digitalWrite(i, LOW);

    // Intial Diagnostic loop to eye check LEDs are wired correctly.
    for(i=22; i<42; i++) {
      digitalWrite(i, HIGH);
      delay(500);
      digitalWrite(i, LOW);
    } 

    for(i=22; i<42; i++) digitalWrite(i, LOW);

    digitalWrite(41, 1); //display impossible LED combination as indication of beginning of setup
    digitalWrite(39, 1);
    digitalWrite(37, 1);
    digitalWrite(35, 1);

    //setup analog pins
    //for(i=0; i<12; i++) pinMode(A0+i, OUTPUT);

    //PORTA: from pin 22 (bit 0) to pin 29 (bit 7)
    //PORTC: from pin 30 (bit 7) to pin 37 (bit 0)
    //PORTD: from pin 38 (bit 7)
    //PORTG: from pin 39 (bit 2) to pin 41 (bit 0)

    //USB-serial port setup
    Serial.begin(115200);

    delay(500);

    //Serial.println("Test");
    
    delay(500);

    //GPS initial setup
    Serial1.begin(9600);
    delay(1500); // wait for GPS to start

    //Software and hardware version
    getVersion(); //does not work on any GPS I tested
    delay(1500);

    setSerial(); //GPS serial port speed 57600 

    delay(1500);
    Serial1.end();
    Serial1.begin(57600);
    delay(1500);

    setRate(); //measurement rate 1Hz

    setSBAS(); //turn off SBAS (suggested in manual)

    setMessage(); //set output message type to none

    setTime(0); //set time system 0-no details, 1-print details
    
    //test GPS and Arduino clock drift rate

    delay(500);

    //setup GPS pin
    pinMode(GPS_pps, INPUT);

    //set external interrupt for 0.1Hz GPS PPS - setup operations
    attachInterrupt(digitalPinToInterrupt(GPS_pps), GPStick, RISING);

    digitalWrite(33, 1); //5 LEDs - waiting for fix

    //wait for fix
    int ini=9;
    if(GPS_wait_for_fix == 1)
    {
        Serial.println("Waiting for fix...");
        GPS_ref_micros = micros();
        us = GPS_ref_micros;
        while(ini>0)
        {
            if(us - GPS_ref_micros > 9900000)
            {
                if( getTM(1)==0 ) //try to identify current GPS tick to make sure that is completely fixed
                {
                    //Serial.print("  tick (passed ");
                    //Serial.print(us - GPS_ref_micros);
                    //Serial.println(" us)");
                    if(us - GPS_ref_micros < 10100000) ini--;
                    GPS_ref_micros = us;
                }
            }
        }
        Serial.println(" fixed");
    }

    Serial.println("Waiting for leap seconds verification...");
    delay(1500);
    int leapsec;
    while(1)
    {
      leapsec=getUTCvalid(0);
      if( leapsec>0 )
      {
        Serial.print("  Current value of GPS leap seconds (GPS-UTC): ");
        Serial.print(leapsec);
        Serial.println(" sec");
        break;
      }
      delay(1500);
    }
    delay(11000);
    Serial.println(" done");

    digitalWrite(31, 1); //6 LEDs - measuring of drift

    //calculate clock drift of Arduino
    ini=9;
    long GPS_ref_micros2=0;
    long us2 = 0;
    long drift[ini];
    int drift_nr=0;
    int ok=1;
    if(GPS_wait_for_drift == 1)
    {
        Serial.println("Calculating Arduino clock drift with respect to GPS");
        Serial.println(" (+ means Arduino clock is too fast)...");
        GPS_ref_micros = micros();
        us = GPS_ref_micros;
        while(1) //wait for GPS PPS signal received - take it as first reference
        {
            if(us > GPS_ref_micros)
            {
                GPS_ref_micros = us;
                break;
            }
        }
        while(ini>0)
        {
            if( (us - GPS_ref_micros) > 9900000 && (us - GPS_ref_micros) < 10100000 ) //check if correct number of seconds has passed
            {
                if( getTM(0)==0 ) //try to identify current GPS tick to make sure that is completely fixed
                {
                    //drift
                    us2=us;
                    GPS_ref_micros2=GPS_ref_micros;
                    drift[drift_nr] = ((us2 - GPS_ref_micros2)-10000000) / 10;
                    //if( drift_nr>0 ) //omitting first reading - sometimes not reliable
                    {
                        Serial.print( "  " );
                        //if( abs(drift[drift_nr]) > Arduino_drift_limit ) ok=0;
                        Serial.print( drift[drift_nr] );
                        Serial.println(" microsec / sec");
                        //Serial.print( us - GPS_ref_micros );
                        //Serial.println(" microsec ");
                    }
                    GPS_ref_micros = us;
                    ini--;
                    drift_nr++;
                }
            }
            else if( us - GPS_ref_micros >= 10100000 )
            {
                GPS_ref_micros = us;
            }
        }

        //sorting drifts
        int test=0;
        long tmp;
        while(test==0)
        {
            test=1;
            for(ini=0; ini<drift_nr-1; ini++)
            {
                if(drift[ini]>drift[ini+1])
                {
                    tmp=drift[ini];
                    drift[ini]=drift[ini+1];
                    drift[ini+1]=tmp;
                    test=0;
                }
            }
        }
        median_drift=drift[drift_nr/2];
        if( abs(median_drift) > Arduino_drift_limit ) ok=0;
        Serial.print("Median drift is ");
        Serial.print(median_drift);
        Serial.println(" arcsec/sec");

#ifndef correct_drift
        if(ok==1)
        {
            Serial.println(" Drift is smaller or equal to the limit - no problem.");
            Serial.println("Starting...");
        }
        else
        {
            Serial.println(" Drift is larger than the limit - clock accuracy might not be as high as 0.0001 sec.");
            Serial.println("Not starting because of too large drift. Reboot for another attempt.");
            digitalWrite(41, 1); //error code - display impossible LED combination
            digitalWrite(40, 0);
            digitalWrite(39, 1);
            for(i=3; i<20; i++) digitalWrite(41-i, 0);
            exit(0);
        }
#endif
    }

    
    digitalWrite(29, 1); //7 LEDs - finished setup

    delay(1500);

    //timer0, timer2: 8-bit
    //timer1, timer3, timer4, timer5: 16-bit

    //timer0: used by delay() millis() micros()
    //timer1: used by servo library
    //timer2: used by tome()

    us = micros();
    last_accepted_us = us;

}

void GPStick() //starting interrupt takes at least 312.5 ns
{
    us = micros();
}

void loop() //this takes 56us during normal clock work
{

digitalWrite(12, 0); //this takes 2us
digitalWrite(12, 1); //this takes 2us
digitalWrite(12, 0); //this takes 2us
digitalWrite(12, 1); //this takes 2us

if( (us - last_us) > 9990000 && (us - last_us) < 10010000 ) last_accepted_us = us; //this is to reduce EMI problems - accept only impulses far enough from last accepted impulse, this takes 800ns
last_us = us;

digitalWrite(12, 0); //this takes 2us

#ifdef correct_drift //this takes 2us
  delta_us=micros()-last_accepted_us;
  delta_us=(delta_us - (median_drift*(long int)delta_us)/1000000)/100; //callibration of delta_us according to measured drift

#else //this takes 2us
  delta_us=(micros()-last_accepted_us)/100; //number of 100us after GPS impulse (this is overflow safe calculation of delta_us)
#endif

  //if, if and else take 1us during normal clock work
  if( stop_work == 1 )
  {
    if( last_accepted_us != old_us ) stop_work=0; //new GPS impulse arrived - go to work
  }
  if( delta_us>100000 ) //this is to prevent running without GPS impulses
  {
    //TIMSK1 = 0; //stop counter - not used - problematic
    digitalWrite(41, 1); //error code - display impossible LED combination
    digitalWrite(40, 0);
    digitalWrite(39, 1);
    digitalWrite(38, 0);
    digitalWrite(37, 1);
    for(i=5; i<20; i++) digitalWrite(41-i, 0);
    stop_work=1;
    old_us = last_accepted_us;
  }
  else if( stop_work==0 && (delta_us - old_delta_us)>0 ) //only change LED display if GPS impulse arrived and internal clock ticked and arrival time was longer than > 9.9 sec
  {

    //first digit takes 11.5um
    m1 = delta_us % 10; //first digit - 100us
    if(m1<1) //turn off all LEDs
    {
      for(i=0; i<4; i++) digitalWrite(22+i, 0);
    }
    else if(m1<5) //turn on 1 LED
    {
      for(i=1; i<5; i++)
      {
         if(i==m1) digitalWrite(21+i, 1);
         else digitalWrite(21+i, 0);
      }
    }
    else if(m1<8) //turn on 2 LEDs
    {
      for(i=5; i<9; i++)
      {
         if(i==m1 || i==(m1+1)) digitalWrite(17+i, 1);
         else digitalWrite(17+i, 0);
      }
    }
    else //turn on 3 and 4 LEDs
    {
      for(i=8; i<12; i++)
      {
         if(i==11 && m1==8) digitalWrite(25, 0);
         else digitalWrite(14+i, 1);
      }
    }

    //second digit takes 11.5um
    m1 = (delta_us/10) % 10; //second digit - 1000us
    if(m1<1) //turn off all LEDs
    {
      for(i=0; i<4; i++) digitalWrite(26+i, 0);
    }
    else if(m1<5) //turn on 1 LED
    {
      for(i=1; i<5; i++)
      {
         if(i==m1) digitalWrite(25+i, 1);
         else digitalWrite(25+i, 0);
      }
    }
    else if(m1<8) //turn on 2 LEDs
    {
      for(i=5; i<9; i++)
      {
         if(i==m1 || i==(m1+1)) digitalWrite(21+i, 1);
         else digitalWrite(21+i, 0);
      }
    }
    else //turn on 3 and 4 LEDs
    {
      for(i=8; i<12; i++)
      {
         if(i==11 && m1==8) digitalWrite(29, 0);
         else digitalWrite(18+i, 1);
      }
    }

    //third digit takes 10.5-11.5um
    m1 = (delta_us/100) % 10; //third digit - 10ms
    if(m1<1) //turn off all LEDs
    {
      for(i=0; i<4; i++) digitalWrite(30+i, 0);
    }
    else if(m1<5) //turn on 1 LED
    {
      for(i=1; i<5; i++)
      {
         if(i==m1) digitalWrite(29+i, 1);
         else digitalWrite(29+i, 0);
      }
    }
    else if(m1<8) //turn on 2 LEDs
    {
      for(i=5; i<9; i++)
      {
         if(i==m1 || i==(m1+1)) digitalWrite(25+i, 1);
         else digitalWrite(25+i, 0);
      }
    }
    else //turn on 3 and 4 LEDs
    {
      for(i=8; i<12; i++)
      {
         if(i==11 && m1==8) digitalWrite(33, 0);
         else digitalWrite(22+i, 1);
      }
    }

    //fourth digit takes 10.0-11.5um
    m1 = (delta_us/1000) % 10; //fourth digit - 100ms
    if(m1<1) //turn off all LEDs
    {
      for(i=0; i<4; i++) digitalWrite(34+i, 0);
    }
    else if(m1<5) //turn on 1 LED
    {
      for(i=1; i<5; i++)
      {
         if(i==m1) digitalWrite(33+i, 1);
         else digitalWrite(33+i, 0);
      }
    }
    else if(m1<8) //turn on 2 LEDs
    {
      for(i=5; i<9; i++)
      {
         if(i==m1 || i==(m1+1)) digitalWrite(29+i, 1);
         else digitalWrite(29+i, 0);
      }
    }
    else //turn on 3 and 4 LEDs
    {
      for(i=8; i<12; i++)
      {
         if(i==11 && m1==8) digitalWrite(37, 0);
         else digitalWrite(26+i, 1);
      }
    }



    //fifth digit takes 10.0-11.5um
    m1 = (delta_us/10000) % 10; //fifth digit - 1s
    if(m1<1) //turn off all LEDs
    {
      for(i=0; i<4; i++) digitalWrite(38+i, 0);
    }
    else if(m1<5) //turn on 1 LED
    {
      for(i=1; i<5; i++)
      {
         if(i==m1) digitalWrite(37+i, 1);
         else digitalWrite(37+i, 0);
      }
    }
    else if(m1<8) //turn on 2 LEDs
    {
      for(i=5; i<9; i++)
      {
         if(i==m1 || i==(m1+1)) digitalWrite(33+i, 1);
         else digitalWrite(33+i, 0);
      }
    }
    else //turn on 3 and 4 LEDs
    {
      for(i=8; i<12; i++)
      {
         if(i==11 && m1==8) digitalWrite(41, 0);
         else digitalWrite(30+i, 1);
      }
    }

    old_delta_us = delta_us; //this takes 0us

  }

}
