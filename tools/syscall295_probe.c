#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <mach/shared_region.h>
#include <mach/vm_prot.h>

#define ROSETTA_SHARED_REGION_MAP_NP_SYSCALL 295

static volatile sig_atomic_t saw_sigsys = 0;

static void
handle_sigsys(int signo)
{
    (void)signo;
    saw_sigsys = 1;
}

int
main(void)
{
    struct sigaction action;
    struct sigaction old_action;
    struct shared_file_mapping_np mapping;
    long result;
    int saved_errno;

    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_sigsys;
    sigemptyset(&action.sa_mask);

    if (sigaction(SIGSYS, &action, &old_action) != 0) {
        perror("sigaction(SIGSYS)");
        return 3;
    }

    memset(&mapping, 0, sizeof(mapping));
    mapping.sfm_address = 0x90000000ULL;
    mapping.sfm_size = 0x1000ULL;
    mapping.sfm_file_offset = 0;
    mapping.sfm_max_prot = VM_PROT_READ;
    mapping.sfm_init_prot = VM_PROT_READ;

    errno = 0;
    result = syscall(ROSETTA_SHARED_REGION_MAP_NP_SYSCALL,
                     -1, 1U, &mapping);
    saved_errno = errno;

    (void)sigaction(SIGSYS, &old_action, NULL);

    printf("syscall295-probe: result=%ld errno=%d saw_sigsys=%d\n",
           result, saved_errno, (int)saw_sigsys);

    if (saw_sigsys) {
        printf("RESULT: FAIL - syscall 295 still generated SIGSYS\n");
        return 2;
    }

    if (result == -1 && saved_errno == EBADF) {
        printf("RESULT: PASS - syscall 295 reached the compatibility front-end and returned EBADF\n");
        return 0;
    }

    printf("RESULT: FAIL - expected result=-1 errno=EBADF(%d) without SIGSYS\n",
           EBADF);
    return 1;
}
