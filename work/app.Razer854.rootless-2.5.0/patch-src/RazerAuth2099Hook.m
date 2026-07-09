#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>

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

static BOOL RZKeyEquals(id key, NSString *s) {
    return [key isKindOfClass:[NSString class]] && [(NSString *)key isEqualToString:s];
}

static id RZForcedObjectForKey(id key, id originalValue) {
    if (!gRazerAuthHookEnabled || ![key isKindOfClass:[NSString class]]) return originalValue;
    NSString *k = (NSString *)key;
    if ([k isEqualToString:@"LicenseAccepted"]) return @YES;
    if ([k isEqualToString:@"ExpiredText"]) return kRazerFutureText;
    // Conservative aliases for expiry predicates seen in similar Razer/Zorro builds.
    NSString *lower = [k lowercaseString];
    if (([lower containsString:@"expire"] || [lower containsString:@"expiry"] || [lower containsString:@"deadline"] || [lower containsString:@"endtime"]) &&
        ([lower containsString:@"time"] || [lower containsString:@"date"] || [lower containsString:@"stamp"])) {
        return RZFutureTimestamp();
    }
    return originalValue;
}

static BOOL RZLooksLikeAuthAlertText(NSString *s) {
    if (![s isKindOfClass:[NSString class]] || s.length == 0) return NO;
    NSArray<NSString *> *needles = @[
        @"未授权", @"未授權", @"Unauthorized", @"unauthorized",
        @"请输入授权码", @"請輸入授權碼", @"Please Input LicenseCode", @"LicenseCode",
        @"license expired", @"授權碼", @"授权码"
    ];
    for (NSString *n in needles) {
        if ([s rangeOfString:n options:NSCaseInsensitiveSearch].location != NSNotFound) return YES;
    }
    return NO;
}

static NSString *RZSanitizedText(NSString *text) {
    if (![text isKindOfClass:[NSString class]]) return text;
    if ([text containsString:@"1970.01.01"] || [text containsString:@"1970-01-01"]) return kRazerFutureText;
    if ([text rangeOfString:@"未授权"].location != NSNotFound || [text rangeOfString:@"未授權"].location != NSNotFound ||
        [text rangeOfString:@"Unauthorized" options:NSCaseInsensitiveSearch].location != NSNotFound ||
        [text rangeOfString:@"license expired" options:NSCaseInsensitiveSearch].location != NSNotFound) {
        return kRazerFutureText;
    }
    return text;
}

@interface NSUserDefaults (RazerAuth2099Hook)
@end
@implementation NSUserDefaults (RazerAuth2099Hook)
- (id)rz2099_objectForKey:(NSString *)defaultName { return RZForcedObjectForKey(defaultName, [self rz2099_objectForKey:defaultName]); }
- (NSString *)rz2099_stringForKey:(NSString *)defaultName {
    id v = RZForcedObjectForKey(defaultName, nil);
    if (v) return [v isKindOfClass:[NSString class]] ? v : [v stringValue];
    return [self rz2099_stringForKey:defaultName];
}
- (BOOL)rz2099_boolForKey:(NSString *)defaultName {
    if (RZKeyEquals(defaultName, @"LicenseAccepted")) return YES;
    return [self rz2099_boolForKey:defaultName];
}
- (NSInteger)rz2099_integerForKey:(NSString *)defaultName {
    if (RZKeyEquals(defaultName, @"LicenseAccepted")) return 1;
    id v = RZForcedObjectForKey(defaultName, nil);
    if (v) return [v integerValue];
    return [self rz2099_integerForKey:defaultName];
}
- (double)rz2099_doubleForKey:(NSString *)defaultName {
    if (RZKeyEquals(defaultName, @"LicenseAccepted")) return 1.0;
    id v = RZForcedObjectForKey(defaultName, nil);
    if (v) return [v doubleValue];
    return [self rz2099_doubleForKey:defaultName];
}
@end

@interface UILabel (RazerAuth2099Hook)
@end
@implementation UILabel (RazerAuth2099Hook)
- (void)rz2099_setText:(NSString *)text { [self rz2099_setText:RZSanitizedText(text)]; }
@end

@interface UIViewController (RazerAuth2099Hook)
@end
@implementation UIViewController (RazerAuth2099Hook)
- (void)rz2099_presentViewController:(UIViewController *)vc animated:(BOOL)flag completion:(void (^)(void))completion {
    if (gRazerAuthHookEnabled && [vc isKindOfClass:[UIAlertController class]]) {
        UIAlertController *alert = (UIAlertController *)vc;
        if (RZLooksLikeAuthAlertText(alert.title) || RZLooksLikeAuthAlertText(alert.message)) {
            if (completion) completion();
            return;
        }
    }
    [self rz2099_presentViewController:vc animated:flag completion:completion];
}
@end

static void RZExchange(Class cls, SEL original, SEL replacement) {
    Method m1 = class_getInstanceMethod(cls, original);
    Method m2 = class_getInstanceMethod(cls, replacement);
    if (m1 && m2) method_exchangeImplementations(m1, m2);
}

static void RZInstallUIKitHooks(void) {
    static BOOL installed = NO;
    if (installed) return;
    installed = YES;
    Class label = NSClassFromString(@"UILabel");
    Class vc = NSClassFromString(@"UIViewController");
    if (label) RZExchange(label, @selector(setText:), @selector(rz2099_setText:));
    if (vc) RZExchange(vc, @selector(presentViewController:animated:completion:), @selector(rz2099_presentViewController:animated:completion:));
    NSLog(@"[RazerAuth2099Hook] post-launch hooks installed");
}

__attribute__((constructor)) static void RazerAuth2099Init(void) {
    @autoreleasepool {
        gRazerAuthHookEnabled = RZIsTargetProcess();
        if (!gRazerAuthHookEnabled) return;

        // Keep constructor work minimal. 2.5.0-4 touched UILabel/UIViewController
        // here, which initialized UIView while dyld was still running tweak constructors on
        // iOS 15.8.8 and reproducibly aborted in ColorSync/CGColorSpace initialization.
        // UI swizzles are installed only after app launch. Avoid broad NSDictionary swizzling:
        // Frida showed ColorSync/CoreFoundation throwing inside -[NSDictionary objectForKey:]
        // during UIView initialization when dictionary classes are globally exchanged.
        RZExchange(objc_getClass("NSUserDefaults"), @selector(objectForKey:), @selector(rz2099_objectForKey:));
        RZExchange(objc_getClass("NSUserDefaults"), @selector(stringForKey:), @selector(rz2099_stringForKey:));
        RZExchange(objc_getClass("NSUserDefaults"), @selector(boolForKey:), @selector(rz2099_boolForKey:));
        RZExchange(objc_getClass("NSUserDefaults"), @selector(integerForKey:), @selector(rz2099_integerForKey:));
        RZExchange(objc_getClass("NSUserDefaults"), @selector(doubleForKey:), @selector(rz2099_doubleForKey:));

        [[NSNotificationCenter defaultCenter] addObserverForName:@"UIApplicationDidFinishLaunchingNotification"
                                                          object:nil
                                                           queue:[NSOperationQueue mainQueue]
                                                      usingBlock:^(__unused NSNotification *note) {
            RZInstallUIKitHooks();
        }];
        NSLog(@"[RazerAuth2099Hook] enabled: LicenseAccepted=YES ExpiredText=%@; post-launch hooks deferred", kRazerFutureText);
    }
}
