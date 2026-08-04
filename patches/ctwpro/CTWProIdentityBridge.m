#import <CoreFoundation/CoreFoundation.h>
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonCryptor.h>
#import <dlfcn.h>

typedef CCCryptorStatus (*CCCryptFunction)(
    CCOperation,
    CCAlgorithm,
    CCOptions,
    const void *,
    size_t,
    const void *,
    const void *,
    size_t,
    void *,
    size_t,
    size_t *
);
typedef CFTypeRef (*MGCopyAnswerFunction)(CFStringRef);
typedef void (*MSHookFunctionType)(void *, void *, void **);

static NSDictionary<NSString *, NSString *> *gMGAnswers;
static MGCopyAnswerFunction gOriginalMGCopyAnswer;

static NSString *AMGDecryptString(NSString *encoded) {
    CCCryptFunction crypt = (CCCryptFunction)dlsym(RTLD_DEFAULT, "CCCrypt");
    NSData *encrypted = [[NSData alloc]
        initWithBase64EncodedString:encoded
                           options:NSDataBase64DecodingIgnoreUnknownCharacters];
    if (crypt == NULL || encrypted.length == 0) {
        return nil;
    }

    static const uint8_t key[kCCKeySizeAES128] = {
        'A', 'M', 'G', '2', '0', '1', '8'
    };
    size_t outputCapacity = encrypted.length + kCCBlockSizeAES128;
    void *output = calloc(1, outputCapacity);
    if (output == NULL) {
        return nil;
    }

    size_t outputLength = 0;
    CCCryptorStatus status = crypt(
        kCCDecrypt,
        kCCAlgorithmAES,
        kCCOptionPKCS7Padding | kCCOptionECBMode,
        key,
        sizeof(key),
        NULL,
        encrypted.bytes,
        encrypted.length,
        output,
        outputCapacity,
        &outputLength
    );
    if (status != kCCSuccess) {
        free(output);
        return nil;
    }

    NSData *plainData = [NSData dataWithBytesNoCopy:output
                                              length:outputLength
                                        freeWhenDone:YES];
    return [[NSString alloc] initWithData:plainData
                                encoding:NSUTF8StringEncoding];
}

static CFTypeRef PatchedMGCopyAnswer(CFStringRef key) {
    if (key != NULL && CFGetTypeID(key) == CFStringGetTypeID()) {
        NSString *answer = gMGAnswers[(__bridge NSString *)key];
        if (answer != nil) {
            return CFRetain((__bridge CFTypeRef)answer);
        }
    }
    return gOriginalMGCopyAnswer == NULL ? NULL : gOriginalMGCopyAnswer(key);
}

__attribute__((constructor))
static void CTWProIdentityBridgeInitialize(void) {
    @autoreleasepool {
        NSString *bundleIdentifier = [NSBundle mainBundle].bundleIdentifier;
        if (bundleIdentifier.length == 0 ||
            [bundleIdentifier hasPrefix:@"com.apple."] ||
            [bundleIdentifier isEqualToString:@"com.xxdevice.CTWPro"] ||
            [bundleIdentifier isEqualToString:@"com.superdev.AMG"]) {
            return;
        }

        NSDictionary *profile = [NSDictionary dictionaryWithContentsOfFile:
            @"/var/jb/var/mobile/Library/Preferences/AMG/faker.plist"];
        NSDictionary<NSString *, NSString *> *mapping = @{
            @"ProductType": @"Model",
            @"ProductVersion": @"SystemVer",
            @"BuildVersion": @"BuildVersion",
            @"UniqueDeviceID": @"UDID",
            @"SerialNumber": @"SerialNumber",
            @"WiFiAddress": @"WifiAddress",
            @"BluetoothAddress": @"BlueAddress",
            @"UserAssignedDeviceName": @"Name"
        };
        NSMutableDictionary<NSString *, NSString *> *answers =
            [NSMutableDictionary dictionaryWithCapacity:mapping.count];
        for (NSString *answerKey in mapping) {
            NSString *plain = AMGDecryptString(profile[mapping[answerKey]]);
            if (plain.length > 0) {
                answers[answerKey] = plain;
            }
        }
        if (answers.count == 0 ||
            ![answers[@"ProductType"] hasPrefix:@"iPhone"] ||
            answers[@"ProductVersion"].length == 0) {
            return;
        }

        void *target = dlsym(RTLD_DEFAULT, "MGCopyAnswer");
        MSHookFunctionType hook =
            (MSHookFunctionType)dlsym(RTLD_DEFAULT, "MSHookFunction");
        if (target == NULL || hook == NULL) {
            return;
        }
        gMGAnswers = [answers copy];
        hook(target, (void *)PatchedMGCopyAnswer,
             (void **)&gOriginalMGCopyAnswer);
    }
}
