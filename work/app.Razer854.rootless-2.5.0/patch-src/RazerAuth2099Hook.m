#import <Foundation/Foundation.h>
#import <objc/runtime.h>

static BOOL gRazerAuthHookEnabled = NO;
static NSString * const kRazerFutureText = @"2099.01.01 00:00";
static NSNumber *RZFutureTimestamp(void) { return @(4070880000LL); } // 2099-01-01 00:00:00 Asia/Shanghai

static BOOL RZIsTargetProcess(void) {
    NSBundle *bundle = [NSBundle mainBundle];
    NSString *bid = [bundle bundleIdentifier] ?: @"";
    NSString *exe = [[NSProcessInfo processInfo] processName] ?: @"";
    NSString *pathExe = [[bundle executablePath] lastPathComponent] ?: @"";
    return [bid isEqualToString:@"Razer"] || [exe isEqualToString:@"Razer"] || [pathExe isEqualToString:@"Razer"];
}

static id RZForcedObjectForKey(id key, id originalValue) {
    if (!gRazerAuthHookEnabled || ![key isKindOfClass:[NSString class]]) return originalValue;
    NSString *k = (NSString *)key;
    if ([k isEqualToString:@"LicenseAccepted"]) return @YES;
    if ([k isEqualToString:@"ExpiredText"]) return kRazerFutureText;
    NSString *lower = [k lowercaseString];
    if (([lower containsString:@"expire"] || [lower containsString:@"expiry"] || [lower containsString:@"deadline"] || [lower containsString:@"endtime"]) &&
        ([lower containsString:@"time"] || [lower containsString:@"date"] || [lower containsString:@"stamp"])) {
        return RZFutureTimestamp();
    }
    return originalValue;
}

@interface NSUserDefaults (RazerAuth2099Hook)
@end
@implementation NSUserDefaults (RazerAuth2099Hook)
- (id)rz2099_objectForKey:(NSString *)key { return RZForcedObjectForKey(key, [self rz2099_objectForKey:key]); }
- (NSString *)rz2099_stringForKey:(NSString *)key {
    id value = RZForcedObjectForKey(key, nil);
    return value ? ([value isKindOfClass:[NSString class]] ? value : [value stringValue]) : [self rz2099_stringForKey:key];
}
- (BOOL)rz2099_boolForKey:(NSString *)key {
    id value = RZForcedObjectForKey(key, nil);
    return value ? [value boolValue] : [self rz2099_boolForKey:key];
}
- (NSInteger)rz2099_integerForKey:(NSString *)key {
    id value = RZForcedObjectForKey(key, nil);
    return value ? [value integerValue] : [self rz2099_integerForKey:key];
}
- (double)rz2099_doubleForKey:(NSString *)key {
    id value = RZForcedObjectForKey(key, nil);
    return value ? [value doubleValue] : [self rz2099_doubleForKey:key];
}
@end

@interface NSDictionary (RazerAuth2099Hook)
@end
@implementation NSDictionary (RazerAuth2099Hook)
- (id)rz2099_objectForKey:(id)key { return RZForcedObjectForKey(key, [self rz2099_objectForKey:key]); }
- (id)rz2099_objectForKeyedSubscript:(id)key { return RZForcedObjectForKey(key, [self rz2099_objectForKeyedSubscript:key]); }
@end

static void RZExchange(Class cls, SEL original, SEL replacement) {
    Method m1 = class_getInstanceMethod(cls, original);
    Method m2 = class_getInstanceMethod(cls, replacement);
    if (m1 && m2) method_exchangeImplementations(m1, m2);
}

static void RZInstallAuthorizationStateHooks(void) {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        // Run after UIApplication finishes launching. This keeps CoreFoundation and
        // ColorSync initialization outside the dictionary-method exchange window.
        Class dict = objc_getClass("NSDictionary");
        RZExchange(dict, @selector(objectForKey:), @selector(rz2099_objectForKey:));
        RZExchange(dict, @selector(objectForKeyedSubscript:), @selector(rz2099_objectForKeyedSubscript:));
        NSLog(@"[RazerAuth2099Hook] authorization state hooks installed");
    });
}

__attribute__((constructor)) static void RazerAuth2099Init(void) {
    @autoreleasepool {
        gRazerAuthHookEnabled = RZIsTargetProcess();
        if (!gRazerAuthHookEnabled) return;

        Class defaults = objc_getClass("NSUserDefaults");
        RZExchange(defaults, @selector(objectForKey:), @selector(rz2099_objectForKey:));
        RZExchange(defaults, @selector(stringForKey:), @selector(rz2099_stringForKey:));
        RZExchange(defaults, @selector(boolForKey:), @selector(rz2099_boolForKey:));
        RZExchange(defaults, @selector(integerForKey:), @selector(rz2099_integerForKey:));
        RZExchange(defaults, @selector(doubleForKey:), @selector(rz2099_doubleForKey:));

        [[NSNotificationCenter defaultCenter] addObserverForName:@"UIApplicationDidFinishLaunchingNotification"
                                                          object:nil
                                                           queue:[NSOperationQueue mainQueue]
                                                      usingBlock:^(__unused NSNotification *note) {
            RZInstallAuthorizationStateHooks();
        }];
        NSLog(@"[RazerAuth2099Hook] enabled: LicenseAccepted=YES ExpiredText=%@; UI remains untouched", kRazerFutureText);
    }
}
