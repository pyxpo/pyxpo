#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Starts embedded CPython on its own thread and relays the _pyxpo_bridge to Swift.
@interface PyxpoRuntime : NSObject
/// Called on the main queue with a JSON ops batch.
@property (nonatomic, copy, nullable) void (^onOps)(NSString *json);
+ (instancetype)shared;
/// pythonHome: dir holding lib/python3.13; paths: extra sys.path entries.
- (void)startWithHome:(NSString *)pythonHome paths:(NSArray<NSString *> *)paths module:(NSString *)module;
/// Any thread. Delivered on a private serial queue; takes the GIL inside the bridge.
- (void)dispatchEvent:(NSString *)json;
@end

NS_ASSUME_NONNULL_END
