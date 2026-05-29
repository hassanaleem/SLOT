; ModuleID = '../motivating-example/example.smt2'
source_filename = "../motivating-example/example.smt2"

define i1 @SMT(i32 %x, i32 %y, i32 %r) {
b:
  %0 = mul i32 %y, %y
  %1 = mul i32 %x, %x
  %2 = sdiv i32 %1, %0
  %3 = mul i32 %x, %x
  %4 = icmp slt i32 %3, 0
  %5 = select i1 %4, i32 1, i32 -1
  %6 = mul i32 %y, %y
  %7 = icmp eq i32 %6, 0
  %8 = select i1 %7, i32 %5, i32 %2
  %9 = icmp eq i32 %r, %8
  %10 = icmp eq i32 %r, 1
  %11 = icmp eq i32 %y, 0
  %12 = select i1 %11, i1 %10, i1 %9
  %13 = icmp eq i32 %r, 1
  %14 = and i1 %12, %13
  ret i1 %14
}
