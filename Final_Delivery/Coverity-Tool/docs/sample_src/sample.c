#include <string.h>
#include <stdio.h>

#define BUF_SIZE 64

void vulnerable_copy(char *input) {
    char buf[BUF_SIZE];
    // BUFFER_SIZE defect: copies exactly sizeof(buf) without room for NUL
    strncpy(buf, input, sizeof(buf));
    printf("%s\n", buf);
}

void safe_copy(char *input) {
    char buf[BUF_SIZE];
    strncpy(buf, input, sizeof(buf)-1);
    buf[sizeof(buf)-1] = '\0';
    printf("%s\n", buf);
}

int main(int argc, char *argv[]) {
    vulnerable_copy(argv[1]);
    safe_copy(argv[1]);
    return 0;
}
