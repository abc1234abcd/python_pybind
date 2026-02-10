//comments in .cpp script, two slash signs, hash sign before include
#include <iostream> 
/*are directives read and interpreted by what is known as preprocessor. they are special lines interpreted before the comilation of the program
itself begins. In this case, the directive £include <iostream>, instructs the preprocessor to include a section of standard c++ code, known as header
isstream, that allows to perform standard input and output oeprations, such as writing the output of this program(hello world) to the screen.*/



/*int main() initiates the declaration of a function. a type, a name, (), optional parameters, {}. the execution of all c++ programs begins with the main 
function, regardless of where the function is actually located within the script.

{ begining of the function, } the end of the function.

a statement is an expression that can actually produce some effect. eg. std::cout which identifies the standard character output device. 

the insertion oeprator << indicates that what follows is inserted into std::cout.

statement ends up with a semicolon ; All statement must end with a semicolon character.
*/

using namespace std;

/* all elements in the standard c++ library are declared within what is called a namespace: the namespace std, although note that 'explicit qualification' is the only way 
to guarantee that name collisions never happen.

int main(){
    cout << "Hello World!";
}


*/

int main(){
    std::cout << "Hello World!";
}

/*A valid identifier is a sequence of one or more letters, digits, or underscore characters (_). Spaces, punctuation marks, and symbols cannot be part of an identifier.

In addition, identifiers shall always begin with a letter. They can also begin with an underline character (_), but such identifiers are -on most cases- considered reserved for 
compiler-specific keywords or external identifiers, as well as identifiers containing two successive underscore characters anywhere. In no case can they begin with a digit.

Very important: The C++ language is a "case sensitive" language. 

*/


int main(){
    int a, b, result;
    a = 5;
    b = 2;
    a = a + 1 ;
    result = a - b ;
    cout << result;
    return 0;
}


/*

initialization of variables

when the variables are declared, they have an undertermined value until they are assigned a value for the first time. BUT, it is possible for a vraible to have a specific value from the moment 
it is declared. This is called the 'initialization' of the variable.


eg. type identifier = initial_value;

int x = 0 ;

or: type identifier (initial_value); or type indentifier{initial_value};

int x(0);

*/

int main(){
    int a = 5;
    int b(2);
    int c{1};
    int result;
    result = a + c - b ;
    cout << result;
    return 0;
}


/*

atuo and decltype: foo and bar are the same type. if variables are not initialized can also make use of type deduction with the decltype specifier: bar is not initialized.

e.g.

int foo = 0;
decltype(foo) bar;

*/

int foo = 0;
auto bar = foo; 

/*string: compond type that is used in the same way as fundametnal types.

if data type is determined at runtime, then the data type is dynamic. if using auto as an type in c++, the data type is still static.

'endl' is a manipulator ends the line(printing a newline character and flushing the stream.). 
In computing, “flushing a stream” refers to the process of forcing any buffered data in an output stream to be written immediately to its destination.

void type has no storage.


char types: char(at least 8 bits), char16_t(not smaller than char, at least 16 bits), char32(not smaller than char16, at least 32 bits), wchar_t(represent the largest supported char set);

int types: signed and unsigned
signed char(same size as char, at least 8 bits), 
signed short int(not smaller than char, at least 16 bits), 
signed int(not smaller than short, at least 16 bits),
signed long int(not smaller than int, at least 32 bits), 
signed long long int(not smaller than long, at least 64 bits)


floating point types:
float
double(precision not less than float)
long double(precision not less than double)

Boolean: bool 

void type: void 

null pointer: decltype(nullptr)



Note in the panel above that other than char (which has a size of exactly one byte), 
none of the fundamental types has a standard size specified (but a minimum size, at most).

*/

#include<iostream>
#include<string>
using namespace std;

int main(){
    string mystring = "this is a string";
    cout << mystring<< endl;
    return 0;
}


/*constants: are epressions with a fixed value.

A. literals.

eg. a = 5;

c++ allows octal number(base 8, the digits are preceded with a 0 character) and hexadecimal numbers(base 16, the digits are preceded with a 0x) as literal constants.


b. character and string literals are enclosed in quotes:
e.g 
'z'
'p'
"Hello world"
"How do you do?"



typed constant experssions:

e.g const double pi = 3.14;

preprocessor definitions(#define)

*/

#include <iostream>
using namespace std;

const double pi = 3.1415926 ;
const char newline = '\n';

int main(){
    double r = 5.0;
    double circle;

    circle = 2*pi*r ;
    cout << circle;
    cout << newline;
}

#include<iostream>
using namespace std;

#define PI 3.1415
#define NEWLINE '\n'

int main(){
    double r = 5.0;
    double circle;

    circle = 2*PI*r ;
    cout << circle;
    cout << NEWLINE;
}



/*

Operators

1. assignment oeprator: = , assignment operator assigns a value to a variable.

eg.

x = y = z = 6; 

y = 2 + (x = 5)

2. arithmetic oeprators: +, -, *, /, % (modulo).


3. compound assignment: +=, -=, *=, /=, %=, >>=, <<=, &=, ^=, |=

price *= units + 1; price = price*(units + 1)

4. increament and decremnt: ++, --

++x; x += 1 ; x = x+1; are equivalent expression.


5. relational and comparison operators: ==, !=, >, <, >=, <=


6. logical operators: !, &&, || 

|| correspons to the Boolean logical operation OR, which yields true if either of its operands is true, thus being false ONLY when BOTH operatnds are false.

&& correspons to the Boolean logical operation AND, which yields true if both its oeprands are true, and false otherwise.

However: 

operator	short-circuit
&&	if the left-hand side expression is false, the combined result is false (the right-hand side expression is never evaluated).
||	if the left-hand side expression is true, the combined result is true (the right-hand side expression is never evaluated).


7. conditional ternary operator: ?

the conditional oeprator evaluates an expression, returning one value if that expression evaluates to true, and different one if the expression evaluates as false.

condition ? result1 : result 2;


e.g 7 == 5 ? 4 : 3 // 3 since 7 is not equal to 5.


8. comma operator: is used to separate two or more expressions that are included where only one expression is expected. when the set of expressions has to be evaluated for a value, only 
the right-most expression is considered. 

a = (b = 3, b+2); a is expected contain the value 5.

9. bitwise operators: &, |, ^, ~, <<, >>, bitwise operators modify variables considering the bit patterns that represent the values they store.

10. explicit type cacsting operator: ()

11. sizeof: this oeprator accepts one parameter, which can be either a tupe or a variable, and returns the size in bytes of that type or object.

e.g 

x = sizeof(char);

*/


int i;
float f = 3.14;
// i =(int) f; or i = int (f);



/*

Basic input and output:

c++ use abstraction caled 'sterams' to perform input and output oerpations in sequential media such as the screen, the keyboard or a file.

a stream is an entity where a prgoram can either insert or extract characters to/from. There is no need to know details about the media associated to the stream or 
any of its internal specifications. All we need to know is htat streams are a source/destination of characters, and that these characters are provided/accepted sequentially.


stream	description
cin	standard input stream
cout	standard output stream
cerr	standard error (output) stream
clog	standard logging (output) stream

e.g cout << "this is" << "a single c++" << "statement"; or cout << "i am here" << endl;

7
the 'endl' manipulator is the same as the insertion of '\n' does, but it also has an additional behaviour: the steam's buffer(if any) is flushed, which means that the output
is requested to be physically written to the device, if it wasnot already. This affects mainly fully buffered streams, and cout is (generally) not a fully buffered stream. 
Still, it is generally a good idea to use endl only when flushing the stream would be a feature and '\n' when it would not. Bear in mind that a flushing operation incurs a certain overhead, 
and on some devices it may produce a delay.

eg. 

int age;
cin >> age; 
cin>> a >> b; is equivelent to : cin>>a; cin>>b;

stringstream <sstream> that allows a string to be treated as a stream. this feature i smost useful to convert strings to numberical values and vice 
versa.

*/



/*

statement and flow control: a simple statement is each of the individual instructions fo a program, like the variable 
declarations and expressions seen in previous sections. A compound statement is a group of statements(each of them terminated by its own semicolon),
but all grouped together in a block, enclosed in curly braces {}.

{statement1; statement2; statement3;} the entire block is considered a single statement. 

eg. selection statement: if and else 

if (condition) statement

if condition is true, statement is executed. if it is false, statement is not executed(simply ignored).

if (x == 100) { cout << "x is "; cout << x; }

if (condition) statement1 else statement2


iteration statements(loops): while, do, for. 

e.g. while (expression) statement

do statement while (condition);  //it behaves like a while-loop, except that condition is evaluated after the execution of statement instead
of before, guaranteeing at least one execution of statement, even if condition is never fulfilled.



for (initialization; condition; increase) statement;

like the while-loop, this loop repeats statement while condition is true. 

Range-based for loop: for (declaration : range) statement;

*/

#include<iostream>
using namespace std;

int main(){
    int n = 10;

    while (n>0) {
        cout<<n<<", ";
        --n;
    }
    cout << "liftoff!\n";
}

int main(){
    for (int n = 10; n>0; n--){
        cout << n <<", ";
    }
    cout << "liftoff!\n";
}


//range loop 
int main(){
    string str {"hello!"};
    for (char c : str){
        cout <<"["<<c<<"]";
    }
    cout << '\n';
}

//jump statements: allow altering the flow of a program by performing jumps to specific locations. eg. break, continue, 



// The goto statement: goto allows to make an absolute jump to another point in the program. This unconditional jump ignores netsting levels, and doesnot not 
//cause automatic stack unwinding. Therefore, it is a feature to use with care, and pereferably within the same block of statements.

int main(){
    int n = 10;
    mylabel:
        cout<<n<<", ";
        n--;
        if (n>0) goto mylabel;
        cout<<"liftoff!\n";
}

//**switch**: its purpose is to check for a value among a number of possible constant expressions. similar with if-else statements, but limited to constant expresssions.



/*

Functions: no matter the order in which functions are defined, a c++ program always starts by calling main. in fact, main is the only function called 
automatically, and the code in any other function is only executed if its function is called from main.


e.g.
type identifier/name (parameter1, parameter 2, ...) { statements} 


function with no type: 'void', when the function doesnot need to return a value at all. void, which is a special type to represent the absence of value.


return value of main function: 

if the execution of main ends normally without encountering a return statement, the compiler sassumes the function ends with an implicit return 
statement 'return 0;'. when main returns zero(either implicitly or explicitly), it is interpreted by the environment as that the program ended 
successfully.


arguments passed by value and by reference: & mean the parameters are passed by reference.


efficency considerations and const references: 


the cmd: cmake .. only locate the CMakeLists.txt file in the root and then 'generates build system files inside build/' folder.  that is, only prepares the build.

then use cmd: make or cmake --build . to reads the generated Makefile, compiles .cpp files to .o , links .o with executable/library.


so in the code-side: CMakeLists.txt -> Makefile -> Binary (cmake.., make/cmake --build .)

*/



/*

best practise principles on low latency c++ 

1. zero dynamic allowcation on hot path
2. cache friendly data structures
3 lock-free where possible
4. clear separation of I/O , parsing, and dispatch
5. deterministic latency
6. fail fast error handling

packed struct: 

e.g 
struct Example {char a; int b;};  c++ will add on padding bytes between  a and b. total bytes will be 8.
v.s 
packed struct: struct __attribute__(packed) PackedExample {char a; int b;}; only 5 bytes in total and c++ will NOT add on padding bytes at all

in c++, sizeof(char) is always 1 byte. a char is 1 byte by definition, but a 'byte' in c++ means CHAR_BIT bits, and is always 8. In char encoding, ASCII, 1 char = 1 byte. 
in UTF-8, one byte is not always 8 bits.


ring buffer(circular buffer) and lock-free ring buffer:

ring buffer: a fixed size buffer that treats memory as circular: when you reach the end, you wrap around to the beginning. use case: storing streaming data(audio, network packets) where old
data can be overwritten. 

benefits of a ring buffer: constant-time insertions and removals, minimal memory allocation. 

constant time in c++: the time it takes to perform an operation does not depend on the size of the data structure, O(1) as in python dict. 
constant-time insertions and removals: means you can add or remove an element without having to traverse or scan the entire data structure.

lock-free ring buffer: is designed for concurrent acccess by multiple threads without using mutexes.
that is, one thread can push data, another can pop data simultaneously. no lock = high performance, low contention.
key idea of lock free ring buffer: only use atomic operations for head tail pointers.


*/


//in c++, namespace is a way to group identifiers(like variables, functions, classes) to avoid name collisions. the std lib like cout, cin, string is in the std namespace.


//atomic in c++: indivisible, not all-or-nothing like an transaction. Atomic = the operation canot be observed half-done. aka, one single, indivisible step, cannot be interrupted,
// and is never seen in a partially updated state. atomics works for: Counters, Flags, Head/tail in ring buffers.


//overflow: happens when a value is too large or too small to be represented bya given data type, as every numeric type has a finite range.
//when a computation or assignment produces a value outside that range, overflow occurs. 


/*

std::mutex 

sychronize primitive that can be used to protect shared data from being simulteneously accessed by multiple threads.



StandardLayoutTYpe(since c++ 11)


*/